import uuid


class AmbulanceDispatchService:
    """Boundary for ambulance integration.

    In production this should call an approved emergency provider, 108/112 partner,
    hospital command center, or state EMS gateway. The service returns a reference
    so the request is auditable even when the external system is asynchronous.
    """

    def request_dispatch(self, *, patient_id: str, symptoms: str, location_text: str) -> str:
        return f"EMS-DEMO-{patient_id[:8]}-{uuid.uuid4().hex[:8]}".upper()
