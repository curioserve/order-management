from flask import Flask, render_template, request, redirect, url_for, flash, session
import csv
from OrderManagment import Order, Operation, OperationStatus
from datetime import datetime, timedelta
from collections import defaultdict
import json

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'  # Required for flash messages

# Global variable to store orders
orders = {}

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
                
                # Parse processing times (in seconds)
                processing_times = {}
                for pt in row['processing_times'].split(';'):
                    machine, time = pt.split(':')
                    processing_times[machine] = float(time)
                
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
    
    # Sort all operations by priority (forced first) and earliest start time
    all_operations = []
    for order in orders.values():
        for operation in order.get_operation_sequence():
            all_operations.append((order, operation))
    
    # Sort by forced status and earliest possible start time
    all_operations.sort(key=lambda x: (
        -x[0].is_forced,  # Forced orders first
        x[1].sequence_number,
        x[0].created_at
    ))
    
    # Schedule operations
    for order, operation in all_operations:
        # Find earliest available machine
        earliest_end = current_time
        selected_machine = None
        
        for machine in operation.capable_machines:
            if machine not in machine_schedule:
                selected_machine = machine
                break
                
            last_op_end = machine_schedule[machine][-1][3] if machine_schedule[machine] else current_time
            if last_op_end < earliest_end:
                earliest_end = last_op_end
                selected_machine = machine
        
        if selected_machine:
            duration = operation.processing_times[selected_machine]
            start_time = earliest_end
            end_time = start_time + timedelta(seconds=duration)
            
            machine_schedule[selected_machine].append((
                order,
                operation,
                start_time,
                end_time
            ))
    
    # Sort each machine's schedule by start time
    for machine in machine_schedule:
        machine_schedule[machine].sort(key=lambda x: x[2])
    
    return machine_schedule, {}, set()

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
                'start_time_str': start_time.strftime('%H:%M:%S'),
                'end_time_str': end_time.strftime('%H:%M:%S'),
                'duration': format_duration((end_time - start_time).total_seconds())
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
                    'start_time_str': start_time.strftime('%H:%M:%S'),
                    'end_time_str': end_time.strftime('%H:%M:%S'),
                    'progress_percentage': round(progress, 1),
                    'remaining_time': remaining_time,
                    'operation_duration': format_duration(total_duration),
                    'elapsed_time': format_duration(elapsed_time),
                    'total_duration': total_duration
                })
                current_operation = operation
            elif start_time > current_time:
                upcoming_operations.append({
                    'order_code': order.order_code,
                    'operation_name': operation.name,
                    'start_time_str': start_time.strftime('%H:%M:%S'),
                    'end_time_str': end_time.strftime('%H:%M:%S'),
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
                'operation_duration': "00:00:00",
                'elapsed_time': "00:00:00"
            })
    
    return machine_status

def format_duration(seconds):
    """Convert seconds to a human-readable format"""
    if not isinstance(seconds, (int, float)):
        return "00:00:00"
    
    # Convert to integer to handle float values
    total_seconds = int(seconds)
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    remaining_seconds = total_seconds % 60
    return f"{hours:02d}:{minutes:02d}:{remaining_seconds:02d}"

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
    # Use the global orders instead of loading from CSV
    global orders
    total_orders = len(orders)
    # Schedule orders
    machine_schedule, order_status, halted_orders = schedule_orders(orders)
    
    # Calculate total statistics
    total_orders = len(orders)
    total_remaining_time = sum(order.get_remaining_time() for order in orders.values())
    total_progress = sum(order.get_progress_percentage() for order in orders.values()) / total_orders if total_orders > 0 else 0
    
    # Group orders by status
    orders_by_status = {
        OperationStatus.PENDING: [],
        OperationStatus.IN_PROGRESS: [],
        OperationStatus.COMPLETED: []
    }
    
    # Sort orders to put forced orders at the top of in-progress
    for order in orders.values():
        if order.status == OperationStatus.IN_PROGRESS:
            if order.is_forced:
                orders_by_status[OperationStatus.IN_PROGRESS].insert(0, order)
            else:
                orders_by_status[OperationStatus.IN_PROGRESS].append(order)
        else:
            orders_by_status[order.status].append(order)
    
    machine_status = get_machine_status(orders, machine_schedule)
    
    return render_template('index.html',
                         machine_status=machine_status,
                         current_time=datetime.now().isoformat(),  # Convert to ISO format
                         format_duration=format_duration,
                         total_orders=total_orders,
                         total_remaining_time=total_remaining_time,
                         total_progress=total_progress,
                         orders_by_status=orders_by_status,
                         OperationStatus=OperationStatus,
                         machine_schedule=machine_schedule,
                         calculate_total_order_time=calculate_total_order_time,
                         min=min,
                         get_min_processing_time=get_min_processing_time,
                         halted_orders=halted_orders)

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
                machine_schedule, order_status, halted_orders = schedule_orders(orders)
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
                machine_schedule, order_status = schedule_orders(orders)
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

if __name__ == '__main__':
    # Initialize orders when starting the app
    load_orders_from_csv()
    app.run(debug=True)