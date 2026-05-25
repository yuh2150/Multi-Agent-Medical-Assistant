class BookingAgentException(Exception):
    """Base exception for all Booking Agent errors."""
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message

class BackendAPIError(BookingAgentException):
    """Exception raised when the Backend API returns an error or fails."""
    def __init__(self, message: str, status_code: int = None):
        super().__init__(message)
        self.status_code = status_code

class UnauthorizedError(BackendAPIError):
    """Exception raised when the customer JWT token is missing or invalid (401)."""
    def __init__(self, message: str = "Phiên làm việc đã hết hạn hoặc không hợp lệ. Vui lòng đăng nhập lại."):
        super().__init__(message, status_code=401)

class DoctorNotFoundError(BookingAgentException):
    """Exception raised when no doctor matches the search criteria."""
    def __init__(self, doctor_name: str = None, specialty_name: str = None):
        msg = "Không tìm thấy bác sĩ phù hợp."
        if doctor_name:
            msg = f"Không tìm thấy bác sĩ nào có tên '{doctor_name}'."
        elif specialty_name:
            msg = f"Không tìm thấy bác sĩ nào thuộc chuyên khoa '{specialty_name}'."
        super().__init__(msg)

class MultipleDoctorsError(BookingAgentException):
    """Exception raised when multiple doctors match the query and user needs to select one."""
    def __init__(self, doctors: list):
        super().__init__("Tìm thấy nhiều bác sĩ phù hợp. Vui lòng chọn bác sĩ mong muốn.")
        self.doctors = doctors

class NoAvailableSlotsError(BookingAgentException):
    """Exception raised when there are no empty slots for a doctor on a specific date."""
    def __init__(self, doctor_name: str, date: str):
        super().__init__(f"Bác sĩ {doctor_name} không có lịch trống vào ngày {date}. Vui lòng chọn ngày khác.")

class InvalidDateError(BookingAgentException):
    """Exception raised when the provided date is invalid or in the past."""
    def __init__(self, date_str: str, message: str = None):
        msg = message or f"Ngày khám '{date_str}' không hợp lệ hoặc đã qua. Vui lòng chọn một ngày trong tương lai."
        super().__init__(msg)

class InvalidTimeSlotError(BookingAgentException):
    """Exception raised when the requested time slot is invalid or not available."""
    def __init__(self, time_str: str, available_slots: list = None):
        msg = f"Thời gian khám '{time_str}' không hợp lệ hoặc đã có người đặt."
        super().__init__(msg)
        self.time_str = time_str
        self.available_slots = available_slots or []

class AppointmentConflictError(BackendAPIError):
    """Exception raised when there is a scheduling conflict (409)."""
    def __init__(self, message: str = "Khung giờ này đã được đặt hoặc bị trùng lịch. Vui lòng chọn giờ khác."):
        super().__init__(message, status_code=409)
