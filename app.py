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
    machine_schedule = defaultdict(list)  # List of (order, operation, start_time, end_time) for each machine
    order_status = {}  # Track current operation for each order
    halted_orders = set()  # Track which orders were halted
    
    # First, preserve all in-progress operations
    in_progress_operations = []
    for order in orders.values():
        for operation in order.get_operation_sequence():
            if operation.status == OperationStatus.IN_PROGRESS and operation.assigned_machine:
                in_progress_operations.append((order, operation, operation.start_time, operation.completion_time))
                machine_schedule[operation.assigned_machine].append((order, operation, operation.start_time, operation.completion_time))
    
    # Then handle forced orders
    forced_orders = [order for order in orders.values() if order.is_forced]
    if forced_orders:
        # For each forced order, find and halt any conflicting operations
        for order in forced_orders:
            # Find all machines needed for this order
            needed_machines = set()
            for operation in order.get_operation_sequence():
                needed_machines.update(operation.capable_machines)
            
            # Halt any operations using these machines
            for machine in needed_machines:
                if machine in machine_schedule:
                    for existing_order, existing_operation, _, _ in machine_schedule[machine]:
                        if existing_order != order and existing_operation.status == OperationStatus.IN_PROGRESS:
                            # Halt the operation
                            existing_operation.status = OperationStatus.PENDING
                            existing_operation.start_time = None
                            existing_operation.completion_time = None
                            existing_operation.assigned_machine = None
                            halted_orders.add(existing_order.order_code)
            
            # Now schedule the forced order
            has_in_progress = False
            all_completed = True
            
            for operation in order.get_operation_sequence():
                # Find the earliest available machine
                earliest_start = current_time
                selected_machine = None
                
                for machine in operation.capable_machines:
                    machine_operations = machine_schedule[machine]
                    if not machine_operations:  # Machine is free
                        selected_machine = machine
                        break
                    
                    # Check if machine will be free before other operations
                    last_operation = machine_operations[-1]
                    if last_operation[3] < earliest_start:
                        earliest_start = last_operation[3]
                        selected_machine = machine
                
                if selected_machine:
                    # Schedule the operation
                    start_time = earliest_start
                    end_time = start_time + timedelta(seconds=operation.processing_times[selected_machine])
                    machine_schedule[selected_machine].append((order, operation, start_time, end_time))
                    
                    # Update operation status
                    operation.status = OperationStatus.IN_PROGRESS
                    operation.assigned_machine = selected_machine
                    operation.start_time = start_time
                    operation.completion_time = end_time
                    has_in_progress = True
                    all_completed = False
                    
                    # Update order status
                    order_status[order.order_code] = operation
                else:
                    # If no machine is available, keep operation pending
                    operation.status = OperationStatus.PENDING
                    operation.assigned_machine = None
                    operation.start_time = None
                    operation.completion_time = None
                    all_completed = False
            
            # Update order status
            if all_completed:
                order.status = OperationStatus.COMPLETED
                order.unforce_order()
            elif has_in_progress:
                order.status = OperationStatus.IN_PROGRESS
            else:
                order.status = OperationStatus.PENDING
    
    # Then handle remaining orders
    remaining_orders = [order for order in orders.values() if not order.is_forced]
    for order in remaining_orders:
        has_in_progress = False
        all_completed = True
        
        for operation in order.get_operation_sequence():
            if operation.status == OperationStatus.IN_PROGRESS:
                has_in_progress = True
                all_completed = False
                continue
                
            # Find the earliest available machine
            earliest_start = current_time
            selected_machine = None
            
            for machine in operation.capable_machines:
                machine_operations = machine_schedule[machine]
                if not machine_operations:  # Machine is free
                    selected_machine = machine
                    break
                
                # Check if machine will be free before other operations
                last_operation = machine_operations[-1]
                if last_operation[3] < earliest_start:
                    earliest_start = last_operation[3]
                    selected_machine = machine
            
            if selected_machine:
                # Schedule the operation
                start_time = earliest_start
                end_time = start_time + timedelta(seconds=operation.processing_times[selected_machine])
                machine_schedule[selected_machine].append((order, operation, start_time, end_time))
                
                # Update operation status
                operation.status = OperationStatus.IN_PROGRESS
                operation.assigned_machine = selected_machine
                operation.start_time = start_time
                operation.completion_time = end_time
                has_in_progress = True
                all_completed = False
                
                # Update order status
                order_status[order.order_code] = operation
            else:
                # If no machine is available, keep operation pending
                operation.status = OperationStatus.PENDING
                operation.assigned_machine = None
                operation.start_time = None
                operation.completion_time = None
                all_completed = False
        
        # Update order status
        if all_completed:
            order.status = OperationStatus.COMPLETED
        elif has_in_progress:
            order.status = OperationStatus.IN_PROGRESS
        else:
            order.status = OperationStatus.PENDING
    
    return machine_schedule, order_status, halted_orders

def get_machine_status(orders):
    machine_status = {}
    current_time = datetime.now()
    
    # Initialize all machines (M1-M45) as idle
    for i in range(1, 46):
        machine_status[f'M{i}'] = {
            'status': 'idle',
            'current_order': None,
            'current_operation': None,
            'start_time': None,
            'end_time': None
        }
    
    # Check each order's operations
    for order in orders.values():
        for operation in order.get_operation_sequence():
            if operation.status == OperationStatus.IN_PROGRESS and operation.assigned_machine:
                machine = operation.assigned_machine
                start_time = operation.start_time
                end_time = operation.completion_time
                
                # Only show as busy if the operation is currently running
                if start_time and end_time and start_time <= current_time <= end_time:
                    machine_status[machine] = {
                        'status': 'busy',
                        'current_order': order.order_code,
                        'current_operation': operation.name,
                        'start_time': start_time,
                        'end_time': end_time
                    }
                else:
                    # If operation is not currently running, mark machine as idle
                    machine_status[machine] = {
                        'status': 'idle',
                        'current_order': None,
                        'current_operation': None,
                        'start_time': None,
                        'end_time': None
                    }
    
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
    
    # Get machine status
    machine_status = get_machine_status(orders)
    
    return render_template('index.html',
                         orders=orders,
                         total_orders=total_orders,
                         total_remaining_time=total_remaining_time,
                         total_progress=total_progress,
                         orders_by_status=orders_by_status,
                         OperationStatus=OperationStatus,
                         machine_status=machine_status,
                         current_time=datetime.now(),
                         machine_schedule=machine_schedule,
                         format_duration=format_duration,
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