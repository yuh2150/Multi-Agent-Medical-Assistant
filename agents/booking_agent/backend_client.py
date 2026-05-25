import httpx
import logging
from typing import Dict, List, Any, Optional
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from .config import booking_config
from .errors import (
    BackendAPIError,
    UnauthorizedError,
    AppointmentConflictError
)

logger = logging.getLogger("booking_agent.backend_client")

class BackendClient:
    """Async HTTP Client to communicate with Backend Server with retries and timeout."""
    
    def __init__(self):
        self.base_url = booking_config.backend_url
        self.timeout = httpx.Timeout(booking_config.http_timeout)
        
    def _get_headers(self, jwt_token: Optional[str] = None) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        if jwt_token:
            # Handle both Bearer prefixed and raw token formats
            if not jwt_token.startswith("Bearer "):
                headers["Authorization"] = f"Bearer {jwt_token}"
            else:
                headers["Authorization"] = jwt_token
        return headers

    def _handle_error_response(self, response: httpx.Response, context: str):
        """Map HTTP error status codes to custom exceptions."""
        status_code = response.status_code
        try:
            error_data = response.json()
            message = error_data.get("message", response.text)
        except Exception:
            message = response.text
            
        logger.error(f"Backend API error during {context}: Code {status_code}, Message: {message}")
        
        if status_code == 401:
            raise UnauthorizedError(message)
        elif status_code == 409:
            raise AppointmentConflictError(message)
        else:
            raise BackendAPIError(f"Backend API Error during {context}: {message}", status_code=status_code)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        retry=retry_if_exception_type((httpx.NetworkError, httpx.TimeoutException)),
        reraise=True
    )
    async def get_customer_me(self, jwt_token: str) -> Dict[str, Any]:
        """Fetch customer profile from GET /api/customers/me"""
        url = f"{self.base_url}/api/customers/me"
        headers = self._get_headers(jwt_token)
        
        logger.info(f"Calling GET {url}")
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.get(url, headers=headers)
                if response.status_code == 200:
                    return response.json()
                self._handle_error_response(response, "GET /api/customers/me")
            except httpx.RequestError as exc:
                logger.error(f"Network error calling GET {url}: {exc}")
                raise BackendAPIError(f"Không thể kết nối đến máy chủ: {exc}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        retry=retry_if_exception_type((httpx.NetworkError, httpx.TimeoutException)),
        reraise=True
    )
    async def search_doctors(self, name: str) -> List[Dict[str, Any]]:
        """Search doctors by name from GET /api/doctors/search?name=<doctorName>"""
        url = f"{self.base_url}/api/doctors/search"
        params = {"name": name}
        headers = self._get_headers()
        
        logger.info(f"Calling GET {url} with params {params}")
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.get(url, params=params, headers=headers)
                if response.status_code == 200:
                    return response.json()
                self._handle_error_response(response, "GET /api/doctors/search")
            except httpx.RequestError as exc:
                logger.error(f"Network error calling GET {url}: {exc}")
                raise BackendAPIError(f"Không thể kết nối đến máy chủ: {exc}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        retry=retry_if_exception_type((httpx.NetworkError, httpx.TimeoutException)),
        reraise=True
    )
    async def get_doctors_by_specialty(self, specialty_name: str) -> List[Dict[str, Any]]:
        """Fetch doctors by specialty from GET /api/doctors?specialty=<specialtyName>"""
        url = f"{self.base_url}/api/doctors"
        params = {"specialty": specialty_name}
        headers = self._get_headers()
        
        logger.info(f"Calling GET {url} with params {params}")
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.get(url, params=params, headers=headers)
                if response.status_code == 200:
                    return response.json()
                self._handle_error_response(response, "GET /api/doctors?specialty")
            except httpx.RequestError as exc:
                logger.error(f"Network error calling GET {url}: {exc}")
                raise BackendAPIError(f"Không thể kết nối đến máy chủ: {exc}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        retry=retry_if_exception_type((httpx.NetworkError, httpx.TimeoutException)),
        reraise=True
    )
    async def get_specialties(self) -> List[Dict[str, Any]]:
        """Fetch all specialties from GET /api/specialties"""
        url = f"{self.base_url}/api/specialties"
        headers = self._get_headers()
        
        logger.info(f"Calling GET {url}")
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.get(url, headers=headers)
                if response.status_code == 200:
                    return response.json()
                self._handle_error_response(response, "GET /api/specialties")
            except httpx.RequestError as exc:
                logger.error(f"Network error calling GET {url}: {exc}")
                raise BackendAPIError(f"Không thể kết nối đến máy chủ: {exc}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        retry=retry_if_exception_type((httpx.NetworkError, httpx.TimeoutException)),
        reraise=True
    )
    async def get_doctor_plans(self, doctor_id: str, date: str) -> List[Dict[str, Any]]:
        """Fetch doctor plans for a date from GET /api/doctors/:doctorId/plans?date=YYYY-MM-DD"""
        url = f"{self.base_url}/api/doctors/{doctor_id}/plans"
        params = {"date": date}
        headers = self._get_headers()
        
        logger.info(f"Calling GET {url} with params {params}")
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.get(url, params=params, headers=headers)
                if response.status_code == 200:
                    return response.json()
                self._handle_error_response(response, f"GET /api/doctors/{doctor_id}/plans")
            except httpx.RequestError as exc:
                logger.error(f"Network error calling GET {url}: {exc}")
                raise BackendAPIError(f"Không thể kết nối đến máy chủ: {exc}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        retry=retry_if_exception_type((httpx.NetworkError, httpx.TimeoutException)),
        reraise=True
    )
    async def get_available_slots(self, doctor_id: str, date: str) -> List[Dict[str, Any]]:
        """Fetch doctor available time slots for a date from GET /api/doctors/:doctorId/available-slots?date=YYYY-MM-DD"""
        url = f"{self.base_url}/api/doctors/{doctor_id}/available-slots"
        params = {"date": date}
        headers = self._get_headers()
        
        logger.info(f"Calling GET {url} with params {params}")
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.get(url, params=params, headers=headers)
                if response.status_code == 200:
                    return response.json()
                self._handle_error_response(response, f"GET /api/doctors/{doctor_id}/available-slots")
            except httpx.RequestError as exc:
                logger.error(f"Network error calling {url}: {exc}")
                raise BackendAPIError(f"Không thể kết nối đến máy chủ: {exc}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        retry=retry_if_exception_type((httpx.NetworkError, httpx.TimeoutException)),
        reraise=True
    )
    async def create_appointment(self, jwt_token: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Post a new appointment booking through POST /api/appointments"""
        url = f"{self.base_url}/api/appointments"
        headers = self._get_headers(jwt_token)
        
        logger.info(f"Calling POST {url} with payload {payload}")
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(url, headers=headers, json=payload)
                if response.status_code in (200, 201):
                    return response.json()
                self._handle_error_response(response, "POST /api/appointments")
            except httpx.RequestError as exc:
                logger.error(f"Network error calling POST {url}: {exc}")
                raise BackendAPIError(f"Không thể kết nối đến máy chủ: {exc}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        retry=retry_if_exception_type((httpx.NetworkError, httpx.TimeoutException)),
        reraise=True
    )
    async def get_appointment(self, appointment_id: str) -> Dict[str, Any]:
        """Fetch details of an appointment from GET /api/appointments/:id"""
        url = f"{self.base_url}/api/appointments/{appointment_id}"
        headers = self._get_headers()
        
        logger.info(f"Calling GET {url}")
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.get(url, headers=headers)
                if response.status_code == 200:
                    return response.json()
                self._handle_error_response(response, f"GET /api/appointments/{appointment_id}")
            except httpx.RequestError as exc:
                logger.error(f"Network error calling GET {url}: {exc}")
                raise BackendAPIError(f"Không thể kết nối đến máy chủ: {exc}")

# Initialize singleton client
backend_client = BackendClient()
