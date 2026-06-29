import uuid

from sqlalchemy.orm import Session

from app.models.feature_modules import DiseaseOutbreakAlert


class PublicHealthService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_outbreak_alert(
        self,
        *,
        state: str,
        city: str,
        disease: str,
        severity: str,
        message: str,
    ) -> DiseaseOutbreakAlert:
        alert = DiseaseOutbreakAlert(
            id=str(uuid.uuid4()),
            state=state,
            city=city,
            disease=disease,
            severity=severity,
            message=message,
        )
        self.db.add(alert)
        self.db.commit()
        self.db.refresh(alert)
        return alert

    def nearby_facilities(self, *, city: str, state: str) -> list[dict]:
        return [
            {
                "name": f"Government Health Facility - {city}",
                "type": "public_health_facility",
                "state": state,
                "city": city,
                "source": "NHR integration boundary",
            }
        ]

    def outbreak_heatmap(self, *, state: str = "") -> list[dict]:
        query = self.db.query(DiseaseOutbreakAlert).filter(DiseaseOutbreakAlert.active.is_(True))
        if state:
            query = query.filter(DiseaseOutbreakAlert.state == state)
        return [
            {
                "state": alert.state,
                "city": alert.city,
                "disease": alert.disease,
                "severity": alert.severity,
                "message": alert.message,
            }
            for alert in query.all()
        ]
