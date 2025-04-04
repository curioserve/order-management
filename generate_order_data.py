import csv
import random
from datetime import datetime, timedelta

def generate_orders(num_orders=200):
    orders = []
    operations = [
        "Cutting", "Drilling", "Milling", "Turning", "Grinding", "Welding",
        "Assembly", "Testing", "Quality Control", "Packaging", "Shipping"
    ]
    
    # Change time scale: Use days and hours directly
    MIN_DAYS = 1  # Minimum 1 day per order
    MAX_DAYS = 3  # Maximum 3 days per order
    
    # Generate orders
    for i in range(num_orders):
        order_code = f"ORD{i+1:04d}"
        quantity = random.randint(10, 100)
        
        # Generate 4-8 operations per order
        num_operations = random.randint(4, 8)
        
        # Total days and hours for the order
        total_days = random.randint(MIN_DAYS, MAX_DAYS)
        total_hours = random.randint(0, 23)  # Additional hours
        
        # Convert to total hours for easier distribution
        total_hours_to_distribute = total_days * 24 + total_hours
        remaining_hours = total_hours_to_distribute
        
        for j in range(num_operations):
            operation_id = f"OP{j+1:02d}"
            operation_name = random.choice(operations)
            
            # Generate 2-4 capable machines per operation
            num_machines = random.randint(2, 4)
            capable_machines = [f"M{k}" for k in random.sample(range(1, 46), num_machines)]
            
            # Calculate operation time (distribute remaining hours among operations)
            if j == num_operations - 1:  # Last operation gets remaining time
                operation_hours = remaining_hours
            else:
                # Ensure minimum 4 hours per operation
                min_op_hours = min(4, remaining_hours // (num_operations - j))
                max_op_hours = min(remaining_hours - ((num_operations - j - 1) * min_op_hours), 36)  # Max 1.5 days
                operation_hours = random.randint(min_op_hours, max_op_hours)
                remaining_hours -= operation_hours
            
            # Convert hours to days and hours format
            op_days, op_hours = divmod(operation_hours, 24)
            
            # Generate processing times in days/hours format for each machine
            processing_times = {}
            for machine in capable_machines:
                # Add some variation (±10%) to the base operation time
                variation = random.uniform(0.9, 1.1)
                machine_hours = int(operation_hours * variation)
                machine_days, machine_hours = divmod(machine_hours, 24)
                processing_times[machine] = f"{machine_days}D{machine_hours}H"
            
            # Convert processing times to string format
            processing_times_str = ";".join([f"{machine}:{time}" for machine, time in processing_times.items()])
            
            orders.append({
                'order_code': order_code,
                'operation_id': operation_id,
                'operation_name': operation_name,
                'quantity': quantity,
                'capable_machines': ','.join(capable_machines),
                'processing_times': processing_times_str,
                'sequence_number': j + 1
            })
    
    return orders

def save_to_csv(orders, filename='orders_data.csv'):
    fieldnames = ['order_code', 'operation_id', 'operation_name', 'quantity', 
                  'capable_machines', 'processing_times', 'sequence_number']
    
    with open(filename, 'w', newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(orders)

if __name__ == '__main__':
    orders = generate_orders(200)  # Generate 200 orders
    save_to_csv(orders)
    print(f"Generated {len(orders)} order operations")