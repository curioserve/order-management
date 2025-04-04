from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from datetime import datetime, timedelta
from collections import defaultdict
import csv
import json

# Import everything we need from OrderManagment
from OrderManagment import Order, Operation, OperationStatus

app = Flask(__name__, static_folder='static', static_url_path='')
app.secret_key = 'your-secret-key-here'  # Required for flash messages

# Make OperationStatus available globally
app.jinja_env.globals.update(OperationStatus=OperationStatus)

# Global variable to store orders
orders = {}

def dh_format_to_seconds(dh_str):
    """Convert a string in the format 'XD YH ZM' to seconds"""
    # Handle different formats more robustly
    try:
        total_seconds = 0
        
        # Parse days if present
        if 'D' in dh_str:
            days_part = dh_str.split('D')[0]
            total_seconds += int(days_part) * 86400  # 24*60*60 seconds in a day
            dh_str = dh_str.split('D')[1]
        
        # Parse hours if present
        if 'H' in dh_str:
            hours_part = dh_str.split('H')[0]
            total_seconds += int(hours_part) * 3600  # 60*60 seconds in an hour
            dh_str = dh_str.split('H')[1] if 'H' in dh_str and len(dh_str.split('H')) > 1 else ""
        
        # Parse minutes if present
        if 'M' in dh_str:
            minutes_part = dh_str.split('M')[0]
            total_seconds += int(minutes_part) * 60
            dh_str = dh_str.split('M')[1] if 'M' in dh_str and len(dh_str.split('M')) > 1 else ""
        
        # Parse seconds if present
        if 'S' in dh_str:
            seconds_part = dh_str.split('S')[0]
            total_seconds += int(seconds_part)
        
        return total_seconds
    except Exception as e:
        print(f"Error parsing time format '{dh_str}': {e}")
        return 3600  # Default to 1 hour if parsing fails

def format_duration(seconds):
    """Convert seconds to days, hours, minutes, and seconds format"""
    if seconds < 0:
        return "0D 0H 0M 0S"
    
    # Convert to days, hours, minutes, and seconds
    days, remainder = divmod(seconds, 86400)  # 86400 seconds in a day
    hours, remainder = divmod(remainder, 3600)  # 3600 seconds in an hour
    minutes, seconds = divmod(remainder, 60)  # 60 seconds in a minute
    
    # Format based on the duration
    if days > 0:
        return f"{int(days)}D {int(hours)}H {int(minutes)}M {int(seconds)}S"
    elif hours > 0:
        return f"{int(hours)}H {int(minutes)}M {int(seconds)}S"
    else:
        return f"{int(minutes)}M {int(seconds)}S"

def load_orders_from_csv():
    global orders
    if not orders:  # Only load if orders is empty
        orders = {}
        with open('orders_data.csv', 'r') as file:
            reader = csv.DictReader(file)
            for row in reader:
                order_code = row['order_code']
                if order_code not in orders:
                    orders[order_code] = Order(
                        order_code=order_code,
                        quantity=int(row['quantity'])
                    )
                    # Ensure order starts as PENDING
                    orders[order_code].status = OperationStatus.PENDING
                    orders[order_code].start_time = None
                    orders[order_code].completion_time = None
                
                # Parse capable machines
                capable_machines = row['capable_machines'].split(',')
                
                # Parse processing times (now in 'XD YH' format)
                processing_times = {}
                for pt in row['processing_times'].split(';'):
                    machine, time_str = pt.split(':')
                    # Convert 'XD YH' to seconds for internal processing
                    processing_times[machine] = dh_format_to_seconds(time_str)
                
                # Add operation to order with PENDING status
                operation = Operation(
                    operation_id=row['operation_id'],
                    name=row['operation_name'],
                    capable_machines=capable_machines,
                    processing_times=processing_times,
                    sequence_number=int(row['sequence_number'])
                )
                operation.status = OperationStatus.PENDING
                operation.start_time = None
                operation.completion_time = None
                operation.assigned_machine = None
                operation.completed_quantity = 0
                
                orders[order_code].add_operation(
                    operation_id=row['operation_id'],
                    name=row['operation_name'],
                    capable_machines=capable_machines,
                    processing_times=processing_times,
                    sequence_number=int(row['sequence_number'])
                )
    return orders

def schedule_orders(orders):
    current_time = datetime.now()
    machine_schedule = defaultdict(list)
    halted_orders = set()
    
    # Sort orders by creation time first (depth-first)
    sorted_orders = sorted(orders.values(), key=lambda o: o.created_at)
    
    # Then collect all operations including halted ones
    all_operations = []
    for order in sorted_orders:  # Process orders in creation order
        for operation in order.get_operation_sequence():
            # Add halted operations with remaining time
            if order.is_operation_halted(operation.operation_id):
                halted_data = order.halted_operations[operation.operation_id]
                remaining_time = operation.processing_times[halted_data['machine']] - halted_data['elapsed_time']
                all_operations.append((order, operation, remaining_time))
            else:
                all_operations.append((order, operation, None))

    # Modify sorting key to prioritize earlier created orders
    all_operations.sort(key=lambda x: (
        -x[0].is_forced,
        -int(x[0].is_operation_halted(x[1].operation_id)),
        x[0].created_at,  # Add creation time to sort key
        x[1].sequence_number
    ))
    
    # Schedule operations with conflict resolution
    for order, operation, remaining_time in all_operations:
        # Find earliest available machine that can handle this operation
        best_machine = None
        best_start = current_time + timedelta(days=365)  # Far future
        
        for machine in operation.capable_machines:
            # Get current schedule for this machine
            machine_ops = machine_schedule[machine]
            last_end = current_time if not machine_ops else machine_ops[-1][3]
            
            # Check if this machine can accommodate the operation
            if remaining_time:  # Halted operation resume
                op_duration = remaining_time
            else:
                op_duration = operation.processing_times[machine]
                
            potential_start = max(last_end, current_time)
            
            if potential_start < best_start:
                best_start = potential_start
                best_machine = machine
        
        if best_machine:
            end_time = best_start + timedelta(seconds=op_duration)
            machine_schedule[best_machine].append((
                order,
                operation,
                best_start,
                end_time
            ))
            
            # Halt conflicting operations
            if order.is_forced:
                for other_order in orders.values():
                    if other_order != order:
                        for op in other_order.operations:
                            if op.assigned_machine == best_machine and op.status == OperationStatus.IN_PROGRESS:
                                other_order.halt_operation(op.operation_id)
                                halted_orders.add(other_order)
    
    # After scheduling operations, update their statuses
    for machine_id, scheduled_ops in machine_schedule.items():
        for order, operation, start_time, end_time in scheduled_ops:
            if start_time <= current_time <= end_time:
                if operation.status == OperationStatus.PENDING:
                    try:
                        order.start_operation(operation.operation_id, machine_id)
                        operation.assigned_machine = machine_id
                        operation.start_time = start_time
                        operation.completion_time = end_time
                    except ValueError as e:
                        print(f"Error starting operation: {e}")
            elif current_time > end_time and operation.status != OperationStatus.COMPLETED:
                operation.completed_quantity = order.quantity
                order.complete_operation(operation.operation_id, order.quantity)
    
    # Fix for completed orders: Update order status based on operations completion
    for order in orders.values():
        # Check if all operations are completed
        all_ops_completed = True
        for op in order.operations:
            if op.status != OperationStatus.COMPLETED:
                all_ops_completed = False
                break
                
        if all_ops_completed:
            # Ensure the order is marked as completed
            if order.status != OperationStatus.COMPLETED:
                order.status = OperationStatus.COMPLETED
                order.completion_time = datetime.now()
        elif any(op.status == OperationStatus.IN_PROGRESS for op in order.operations):
            # Ensure the order is marked as in progress
            if order.status == OperationStatus.PENDING:
                order.start_order()

    return machine_schedule, halted_orders

def get_machine_status(orders, machine_schedule):
    """Get detailed status for each machine including current and next operations"""
    machine_status = {}
    current_time = datetime.now()
    
    # Initialize all machines (M1-M45)
    for i in range(1, 46):
        machine_id = f'M{i}'
        machine_status[machine_id] = {
            'status': 'idle',
            'current_order': None,
            'current_operation': None,
            'start_time': None,
            'end_time': None,
            'start_time_str': None,
            'end_time_str': None,
            'progress_percentage': 0,
            'remaining_time': 0,
            'upcoming_operations': [],
            'full_schedule': []
        }
    
    # Process machine schedules
    for machine_id, scheduled_ops in machine_schedule.items():
        scheduled_ops.sort(key=lambda x: x[2])
        current_operation = None
        upcoming_operations = []
        full_schedule = []
        
        for order, operation, start_time, end_time in scheduled_ops:
            schedule_entry = {
                'order_code': order.order_code,
                'operation_name': operation.name,
                'start_time': start_time,
                'end_time': end_time,
                'start_time_str': start_time.strftime('%d-%H:%M:%S'),
                'end_time_str': end_time.strftime('%d-%H:%M:%S'),
                'duration': format_duration((end_time - start_time).total_seconds()),
                'is_completed': operation.status == OperationStatus.COMPLETED
            }
            full_schedule.append(schedule_entry)
            
            if start_time <= current_time <= end_time:
                total_duration = (end_time - start_time).total_seconds()
                elapsed_time = (current_time - start_time).total_seconds()
                progress = min(100, (elapsed_time / total_duration) * 100 if total_duration > 0 else 0)
                remaining_time = max(0, (end_time - current_time).total_seconds())
                
                machine_status[machine_id].update({
                    'status': 'busy',
                    'current_order': order.order_code,
                    'current_operation': operation.name,
                    'start_time': start_time,
                    'end_time': end_time,
                    'start_time_str': start_time.strftime('%d-%H:%M:%S'),
                    'end_time_str': end_time.strftime('%d-%H:%M:%S'),
                    'progress_percentage': round(progress, 1),
                    'remaining_time': remaining_time,
                    'operation_duration': format_duration(total_duration),
                    'elapsed_time': format_duration(elapsed_time),
                    'total_duration': total_duration,
                    'start_timestamp': start_time.timestamp(),
                    'end_timestamp': end_time.timestamp()
                })
                current_operation = operation
            elif start_time > current_time:
                upcoming_operations.append({
                    'order_code': order.order_code,
                    'operation_name': operation.name,
                    'start_time_str': start_time.strftime('%d-%H:%M:%S'),
                    'end_time_str': end_time.strftime('%d-%H:%M:%S'),
                    'duration': format_duration((end_time - start_time).total_seconds())
                })
        
        # Add upcoming operations and full schedule to machine status
        machine_status[machine_id]['upcoming_operations'] = upcoming_operations[:2]
        machine_status[machine_id]['full_schedule'] = full_schedule
        
        # If machine is idle, ensure all fields are properly set
        if not current_operation and not upcoming_operations:
            machine_status[machine_id].update({
                'status': 'idle',
                'current_order': None,
                'current_operation': None,
                'progress_percentage': 0,
                'remaining_time': 0,
                'start_time': None,
                'end_time': None,
                'operation_duration': "0D0H0M0S",
                'elapsed_time': "0D0H0M0S"
            })
    
    # Update the date formats for schedule items
    for schedule_item in full_schedule:
        # Convert timestamps to days, hours, minutes, seconds format
        start_time = schedule_item['start_time']
        end_time = schedule_item['end_time']
        schedule_item['start_time_str'] = start_time.strftime('%d-%H:%M:%S')
        schedule_item['end_time_str'] = end_time.strftime('%d-%H:%M:%S')
        schedule_item['duration'] = format_duration((end_time - start_time).total_seconds())
    
    return machine_status

def calculate_total_order_time(order):
    """Calculate total time for an order based on its operations"""
    total_time = 0
    for operation in order.get_operation_sequence():
        # Get the minimum processing time among capable machines
        min_time = min(operation.processing_times.values())
        total_time += min_time
    return total_time

def get_min_processing_time(operation):
    """Get the minimum processing time for an operation"""
    if not operation.processing_times:
        return 0
    return min(operation.processing_times.values())

@app.route('/')
def index():
    """
    Main page showing order information and controls
    """
    load_orders_from_csv()
    machine_schedule, halted_orders = schedule_orders(orders)
    
    # Force-check for completed orders before rendering
    force_update_order_status()
    
    # Group orders by status
    orders_by_status = defaultdict(list)
    for order in orders.values():
        orders_by_status[order.status].append(order)
    
    # Get machine status
    machine_status = get_machine_status(orders, machine_schedule)
    
    # Calculate total remaining time
    total_remaining_time = sum(order.get_remaining_time() for order in orders.values())
    
    halted_order_objects = [order for order in orders.values() if any(order.is_operation_halted(op.operation_id) for op in order.operations)]
    
    return render_template('index.html',
                          orders=orders.values(),
                          orders_by_status=orders_by_status,
                          machine_status=machine_status,
                          total_remaining_time=format_duration(total_remaining_time),
                          calculate_total_order_time=calculate_total_order_time,
                          format_duration=format_duration,
                          halted_orders={order.order_code: order for order in halted_order_objects},
                          OperationStatus=OperationStatus,
                          get_min_processing_time=get_min_processing_time)

def force_update_order_status():
    """Force update order status based on operations status"""
    for order in orders.values():
        # Check if all operations are completed
        if all(op.status == OperationStatus.COMPLETED for op in order.operations):
            # Set completion time if not already set
            if not order.completion_time:
                order.completion_time = datetime.now()
            # Force order to completed status
            order.status = OperationStatus.COMPLETED
        elif any(op.status == OperationStatus.IN_PROGRESS for op in order.operations):
            order.status = OperationStatus.IN_PROGRESS
            
        # Update operation status for operations showing 100% progress
        for op in order.operations:
            if op.status == OperationStatus.IN_PROGRESS and op.get_progress_percentage() >= 99.9:
                op.status = OperationStatus.COMPLETED
                if not op.completion_time:
                    op.completion_time = datetime.now()

@app.route('/start_operation', methods=['POST'])
def start_operation():
    order_code = request.form.get('order_code')
    operation_id = request.form.get('operation_id')
    machine_id = request.form.get('machine_id')
    
    global orders
    if order_code in orders:
        try:
            orders[order_code].start_operation(operation_id, machine_id)
            flash(f'Started operation {operation_id} on machine {machine_id} for order {order_code}', 'success')
        except ValueError as e:
            flash(str(e), 'error')
    
    return redirect(url_for('index'))

@app.route('/complete_operation', methods=['POST'])
def complete_operation():
    order_code = request.form.get('order_code')
    operation_id = request.form.get('operation_id')
    completed_quantity = int(request.form.get('completed_quantity', 0))
    
    global orders
    if order_code in orders:
        try:
            orders[order_code].complete_operation(operation_id, completed_quantity)
            flash(f'Completed operation {operation_id} for order {order_code}', 'success')
        except ValueError as e:
            flash(str(e), 'error')
    
    return redirect(url_for('index'))

@app.route('/force_order', methods=['POST'])
def force_order():
    order_code = request.form.get('order_code')
    global orders
    
    if order_code in orders:
        order = orders[order_code]
        if order.status == OperationStatus.PENDING:
            try:
                order.force_order()
                # Immediately reschedule all orders
                machine_schedule, halted_orders = schedule_orders(orders)
                if halted_orders:
                    flash(f'Order {order_code} has been forced. Orders {", ".join(halted_orders)} were halted to accommodate it.', 'success')
                else:
                    flash(f'Order {order_code} has been forced to the front of the queue', 'success')
            except Exception as e:
                flash(str(e), 'error')
        else:
            flash(f'Cannot force order {order_code} - only pending orders can be forced', 'error')
    
    return redirect(url_for('index'))

@app.route('/unforce_order', methods=['POST'])
def unforce_order():
    order_code = request.form.get('order_code')
    global orders
    
    if order_code in orders:
        order = orders[order_code]
        if order.is_forced:
            try:
                order.unforce_order()
                # Immediately reschedule all orders
                machine_schedule, halted_orders = schedule_orders(orders)
                flash(f'Order {order_code} has been unforced', 'success')
            except Exception as e:
                flash(str(e), 'error')
        else:
            flash(f'Order {order_code} is not forced', 'error')
    
    return redirect(url_for('index'))

# Add a route to reset the system if needed
@app.route('/reset', methods=['POST'])
def reset():
    global orders
    orders = {}  # Clear the orders
    load_orders_from_csv()  # Reload from CSV
    flash('System has been reset', 'success')
    return redirect(url_for('index'))

# Add CORS headers middleware
@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response

@app.route('/machine_status')
def machine_status():
    try:
        machine_schedule, _ = schedule_orders(orders)
        current_time = datetime.now()
        
        machine_status = {}
        for machine_id, schedule in machine_schedule.items():
            status = {
                'status': 'idle',
                'progress_percentage': 0,
                'remaining_time': 0,
                'start_time': None,
                'end_time': None
            }
            
            current_op = next(
                (op for op in schedule 
                 if op[2] <= current_time <= op[3] and 
                 op[1].status != OperationStatus.COMPLETED),
                None
            )
            
            if current_op:
                order, operation, start, end = current_op
                total_seconds = (end - start).total_seconds()
                elapsed = (current_time - start).total_seconds()
                remaining = max(0, total_seconds - elapsed)
                
                status.update({
                    'status': 'busy',
                    'current_order': order.order_code,
                    'current_operation': operation.name,
                    'start_time': start,
                    'end_time': end,
                    'progress_percentage': min(100, (elapsed / total_seconds) * 100),
                    'remaining_time': remaining
                })
            
            machine_status[machine_id] = status
        
        return render_template('machine_status.html',
                            machine_status=machine_status,
                            machine_schedule=machine_schedule,
                            current_time=current_time,
                            format_duration=format_duration,
                            OperationStatus=OperationStatus)
    
    except Exception as e:
        app.logger.error(f"Error in machine_status: {str(e)}")
        return str(e), 500

@app.route('/api/machine_status')
def api_machine_status():
    try:
        machine_schedule, _ = schedule_orders(orders)
        current_time = datetime.now()
        
        status_data = {}
        for machine_id, schedule in machine_schedule.items():
            current_op = next(
                (op for op in schedule if op[2] <= current_time <= op[3]),
                None
            )
            
            status = {
                'status': 'idle',
                'progress': 0,
                'remaining': 0
            }
            
            if current_op:
                order, operation, start, end = current_op
                total = (end - start).total_seconds()
                elapsed = (current_time - start).total_seconds()
                remaining = max(0, total - elapsed)
                
                status = {
                    'status': 'busy',
                    'current_order': order.order_code,
                    'current_operation': operation.name,
                    'progress': min(100, (elapsed / total) * 100),
                    'remaining': remaining,
                    'end_time': end.timestamp()
                }
            
            status_data[machine_id] = status
        
        return jsonify(status_data)
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    load_orders_from_csv()
    app.run(host='0.0.0.0', port=8080, debug=True)  # Add host and port parameters