from typing import List, Dict
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

class OperationStatus(Enum):
    PENDING = "Pending"
    IN_PROGRESS = "In Progress"
    COMPLETED = "Completed"

@dataclass
class Operation:
    operation_id: str
    name: str
    capable_machines: List[str]  # List of machine IDs that can perform this operation
    processing_times: Dict[str, float]  # Dictionary mapping machine_id to processing time in hours
    sequence_number: int  # Order of operation in the sequence
    status: OperationStatus = OperationStatus.PENDING
    assigned_machine: str = None
    start_time: datetime = None
    completion_time: datetime = None
    completed_quantity: int = 0

    def get_progress_percentage(self):
        """Calculate the progress percentage of the operation"""
        if self.status == OperationStatus.COMPLETED:
            return 100
        elif self.status == OperationStatus.PENDING:
            return 0
        elif self.status == OperationStatus.IN_PROGRESS and self.start_time and self.assigned_machine:
            current_time = datetime.now()
            total_time = self.processing_times[self.assigned_machine]
            elapsed_time = (current_time - self.start_time).total_seconds()
            progress = (elapsed_time / total_time) * 100
            return min(100, max(0, progress))
        return 0

    def get_remaining_time(self):
        """Calculate remaining time for the operation in seconds"""
        if self.status == OperationStatus.COMPLETED:
            return 0
        elif self.status == OperationStatus.PENDING:
            return min(self.processing_times.values()) if self.processing_times else 0
        elif self.status == OperationStatus.IN_PROGRESS and self.start_time and self.assigned_machine:
            current_time = datetime.now()
            total_time = self.processing_times[self.assigned_machine]
            elapsed_time = (current_time - self.start_time).total_seconds()
            remaining = total_time - elapsed_time
            return max(0, remaining)
        return 0

class Order:
    def __init__(self, order_code: str, quantity: int):
        self.order_code = order_code
        self.quantity = quantity
        self.operations: List[Operation] = []
        self.created_at = datetime.now()
        self.status: OperationStatus = OperationStatus.PENDING
        self.start_time: datetime = None
        self.completion_time: datetime = None
        self.is_forced = False
        self.force_time = None
        self.halted_operations = {}  # Store halted operations with their progress
        
    def add_operation(self, operation_id: str, name: str, capable_machines: List[str], 
                     processing_times: Dict[str, float], sequence_number: int) -> None:
        """
        Add a new operation to the order
        
        Args:
            operation_id: Unique identifier for the operation
            name: Name/description of the operation
            capable_machines: List of machine IDs that can perform this operation
            processing_times: Dictionary mapping machine_id to processing time in hours
            sequence_number: Order of operation in the sequence (1-based)
        """
        operation = Operation(
            operation_id=operation_id,
            name=name,
            capable_machines=capable_machines,
            processing_times=processing_times,
            sequence_number=sequence_number
        )
        self.operations.append(operation)
        # Sort operations by sequence number
        self.operations.sort(key=lambda x: x.sequence_number)
    
    def start_order(self) -> None:
        """Start the order processing"""
        if self.status == OperationStatus.PENDING:
            self.status = OperationStatus.IN_PROGRESS
            self.start_time = datetime.now()
    
    def complete_order(self) -> None:
        """Mark the order as completed"""
        if self.status == OperationStatus.IN_PROGRESS:
            self.status = OperationStatus.COMPLETED
            self.completion_time = datetime.now()
    
    def start_operation(self, operation_id: str, machine_id: str) -> None:
        """
        Start a specific operation on a machine
        
        Args:
            operation_id: ID of the operation to start
            machine_id: ID of the machine to use
        """
        operation = self.get_operation_details(operation_id)
        if operation and operation.status == OperationStatus.PENDING:
            if machine_id in operation.capable_machines:
                operation.status = OperationStatus.IN_PROGRESS
                operation.assigned_machine = machine_id
                operation.start_time = datetime.now()
                if not self.start_time:
                    self.start_order()
            else:
                raise ValueError(f"Machine {machine_id} is not capable of operation {operation_id}")
    
    def complete_operation(self, operation_id: str, completed_quantity: int) -> None:
        """
        Complete a specific operation
        
        Args:
            operation_id: ID of the operation to complete
            completed_quantity: Number of items completed in this operation
        """
        operation = self.get_operation_details(operation_id)
        if operation and operation.status == OperationStatus.IN_PROGRESS:
            operation.status = OperationStatus.COMPLETED
            operation.completion_time = datetime.now()
            operation.completed_quantity = completed_quantity
            
            # Check if all operations are completed
            if all(op.status == OperationStatus.COMPLETED for op in self.operations):
                self.complete_order()
    
    def get_progress_percentage(self) -> float:
        """
        Calculate the overall progress percentage of the order
        
        Returns:
            Progress percentage (0-100)
        """
        if not self.operations:
            return 0.0
        
        total_operations = len(self.operations)
        completed_operations = sum(1 for op in self.operations if op.status == OperationStatus.COMPLETED)
        
        if self.status == OperationStatus.COMPLETED:
            return 100.0
        
        if completed_operations == total_operations:
            # All operations are complete, order should be marked complete
            self.complete_order()
            return 100.0
        
        # Calculate progress for each operation
        operation_progress = []
        for op in self.operations:
            if op.status == OperationStatus.COMPLETED:
                operation_progress.append(100.0)
            elif op.status == OperationStatus.IN_PROGRESS:
                # Get actual progress for in-progress operation
                operation_progress.append(op.get_progress_percentage())
            else:
                operation_progress.append(0.0)
        
        # Calculate overall progress
        return sum(operation_progress) / total_operations
    
    def get_remaining_time(self) -> float:
        """
        Estimate remaining time to complete the order
        
        Returns:
            Estimated remaining hours
        """
        if self.status == OperationStatus.COMPLETED:
            return 0.0
        
        remaining_hours = 0
        for operation in self.operations:
            if operation.status == OperationStatus.PENDING:
                # Use the fastest available machine for estimation
                min_time = min(operation.processing_times.values())
                remaining_hours += min_time * (self.quantity - operation.completed_quantity)
            elif operation.status == OperationStatus.IN_PROGRESS:
                # Add remaining time for in-progress operation
                remaining_hours += operation.processing_times[operation.assigned_machine] * (self.quantity - operation.completed_quantity)
        
        return remaining_hours
    
    def get_operation_sequence(self) -> List[Operation]:
        """
        Get operations in their correct sequence
        
        Returns:
            List of operations sorted by sequence number
        """
        return sorted(self.operations, key=lambda x: x.sequence_number)
    
    def estimate_total_hours(self, machine_selection: Dict[str, str] = None) -> float:
        """
        Estimate total hours needed to complete the order
        
        Args:
            machine_selection: Optional dictionary mapping operation_id to selected machine_id
                             If not provided, uses the fastest available machine for each operation
        
        Returns:
            Total estimated hours to complete the order
        """
        total_hours = 0
        
        for operation in self.get_operation_sequence():
            if machine_selection and operation.operation_id in machine_selection:
                # Use the specified machine if provided
                selected_machine = machine_selection[operation.operation_id]
                if selected_machine in operation.processing_times:
                    total_hours += operation.processing_times[selected_machine] * self.quantity
                else:
                    raise ValueError(f"Selected machine {selected_machine} is not capable of operation {operation.operation_id}")
            else:
                # Use the fastest available machine
                min_time = min(operation.processing_times.values())
                total_hours += min_time * self.quantity
                
        return total_hours
    
    def get_operation_details(self, operation_id: str) -> Operation:
        """
        Get details of a specific operation
        
        Args:
            operation_id: ID of the operation to retrieve
            
        Returns:
            Operation object if found, None otherwise
        """
        for operation in self.operations:
            if operation.operation_id == operation_id:
                return operation
        return None
    
    def get_operation_by_sequence(self, sequence_number: int) -> Operation:
        """
        Get operation by its sequence number
        
        Args:
            sequence_number: The sequence number of the operation
            
        Returns:
            Operation object if found, None otherwise
        """
        for operation in self.operations:
            if operation.sequence_number == sequence_number:
                return operation
        return None
    
    def __str__(self) -> str:
        operations_str = "\n".join([
            f"  {op.sequence_number}. {op.name} ({op.operation_id}) - {op.status.value}"
            for op in self.get_operation_sequence()
        ])
        progress = self.get_progress_percentage()
        remaining_time = self.get_remaining_time()
        return (f"Order {self.order_code} (Quantity: {self.quantity}, Status: {self.status.value})\n"
                f"Progress: {progress:.1f}%, Remaining Time: {remaining_time:.1f} hours\n"
                f"Operations:\n{operations_str}")

    def force_order(self) -> None:
        """Mark order as forced and halt conflicting operations"""
        self.is_forced = True
        self.force_time = datetime.now()
        
        # Halt all operations that are using our required machines
        required_machines = set()
        for op in self.operations:
            required_machines.update(op.capable_machines)
        
        # This should be called from the scheduling logic to actually halt others
        # (implementation shown in the schedule_orders function above)

    def unforce_order(self) -> None:
        """Remove force status from the order"""
        self.is_forced = False
        self.force_time = None

    def halt_operation(self, operation_id: str) -> None:
        """Halt an operation and store its progress"""
        operation = self.get_operation_details(operation_id)
        if operation and operation.status == OperationStatus.IN_PROGRESS:
            current_time = datetime.now()
            elapsed_time = (current_time - operation.start_time).total_seconds()
            total_time = operation.processing_times[operation.assigned_machine]
            progress = (elapsed_time / total_time) * 100
            
            self.halted_operations[operation_id] = {
                'progress': progress,
                'elapsed_time': elapsed_time,
                'machine': operation.assigned_machine
            }
            
            operation.status = OperationStatus.PENDING
            operation.start_time = None
            operation.completion_time = None
            operation.assigned_machine = None

    def resume_operation(self, operation_id: str) -> None:
        """Resume a halted operation from its previous progress"""
        operation = self.get_operation_details(operation_id)
        if operation and operation_id in self.halted_operations:
            halted_data = self.halted_operations[operation_id]
            operation.status = OperationStatus.IN_PROGRESS
            operation.assigned_machine = halted_data['machine']
            operation.start_time = datetime.now() - timedelta(seconds=halted_data['elapsed_time'])
            operation.completion_time = operation.start_time + timedelta(seconds=operation.processing_times[operation.assigned_machine])
            del self.halted_operations[operation_id]

    def get_halted_progress(self, operation_id: str) -> float:
        """Get the progress of a halted operation"""
        return self.halted_operations.get(operation_id, {}).get('progress', 0)

    def is_operation_halted(self, operation_id: str) -> bool:
        """Check if an operation is halted"""
        return operation_id in self.halted_operations

    def get_remaining_processing_time(self, operation_id):
        """Get remaining time for halted operation"""
        if operation_id in self.halted_operations:
            halted_data = self.halted_operations[operation_id]
            return halted_data['remaining_time']
        return 0

# Example usage:
if __name__ == "__main__":
    # Create a sample order
    order = Order("ORD001", quantity=100)
    
    # Add operations to the order in sequence
    order.add_operation(
        operation_id="OP001",
        name="Cutting",
        capable_machines=["M1", "M2", "M3"],
        processing_times={"M1": 0.5, "M2": 0.6, "M3": 0.4},
        sequence_number=1
    )
    
    order.add_operation(
        operation_id="OP002",
        name="Welding",
        capable_machines=["M2", "M3", "M4"],
        processing_times={"M2": 1.0, "M3": 1.2, "M4": 0.8},
        sequence_number=2
    )
    
    order.add_operation(
        operation_id="OP003",
        name="Assembly",
        capable_machines=["M3", "M5", "M6"],
        processing_times={"M3": 1.5, "M5": 1.8, "M6": 1.2},
        sequence_number=3
    )
    
    # Print initial order details
    print("Initial order state:")
    print(order)
    
    # Start the first operation
    order.start_operation("OP001", "M3")
    print("\nAfter starting first operation:")
    print(order)
    
    # Complete the first operation
    order.complete_operation("OP001", 50)
    print("\nAfter completing first operation:")
    print(order)
    
    # Start the second operation
    order.start_operation("OP002", "M4")
    print("\nAfter starting second operation:")
    print(order)
    
    # Complete the second operation
    order.complete_operation("OP002", 50)
    print("\nAfter completing second operation:")
    print(order)
    
    # Start and complete the third operation
    order.start_operation("OP003", "M6")
    order.complete_operation("OP003", 100)
    print("\nFinal order state:")
    print(order)