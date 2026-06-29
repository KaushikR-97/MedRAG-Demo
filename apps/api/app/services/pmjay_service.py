from sqlalchemy.orm import Session
from datetime import UTC, datetime

class PmjayMatcherService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def check_eligibility(self, *, diagnosis: str, patient_id: str | None = None) -> dict:
        # Fetch patient labs if patient_id is provided
        labs = []
        if patient_id:
            from app.models.feature_modules import LabResult
            labs = self.db.query(LabResult).filter(LabResult.patient_id == patient_id).all()
        
        diag_lower = diagnosis.lower()
        
        # 1. Dengue Treatment Package Matcher
        if "dengue" in diag_lower:
            platelet_value = None
            for lab in labs:
                if "platelet" in lab.test_name.lower():
                    platelet_value = lab.value
                    break
            
            if platelet_value is not None and platelet_value < 100000:
                return {
                    "eligible": True,
                    "package_name": "Severe Dengue / Dengue Hemorrhagic Fever Management",
                    "package_code": "MG011A",
                    "coverage_amount": 25000.0,
                    "reasoning": f"Diagnosis matches 'Dengue' and lab report platelet count ({platelet_value}) is below the threshold of 100,000 cells/mcL.",
                    "guidelines": [
                        "Attach positive NS1 antigen or IgM ELISA report",
                        "Attach daily platelet monitoring chart",
                        "Attach hospital admission and vitals record sheet"
                    ]
                }
            elif platelet_value is not None:
                return {
                    "eligible": False,
                    "package_name": "Severe Dengue / Dengue Hemorrhagic Fever Management",
                    "package_code": "MG011A",
                    "coverage_amount": 0.0,
                    "reasoning": f"Diagnosis matches 'Dengue' but platelet count ({platelet_value}) is above the clinical threshold (> 100,000) required for PM-JAY package approval.",
                    "guidelines": [
                        "Platelet count must be under 100,000 for emergency admission approval under PM-JAY guidelines."
                    ]
                }
            else:
                return {
                    "eligible": True,
                    "package_name": "Dengue Fever Treatment",
                    "package_code": "MG011B",
                    "coverage_amount": 15000.0,
                    "reasoning": "Diagnosis matches 'Dengue'. Eligible for standard fever package. Upload a platelet count lab report to check eligibility for the high-coverage severe dengue package.",
                    "guidelines": [
                        "Attach NS1 or IgM diagnostic test report",
                        "Upload platelet count lab results if severe thrombocytopenia is suspected"
                    ]
                }

        # 2. Appendectomy Package Matcher
        if any(kw in diag_lower for kw in ["appendicitis", "appendectomy", "appendix"]):
            return {
                "eligible": True,
                "package_name": "Laparoscopic/Open Appendectomy",
                "package_code": "SG015",
                "coverage_amount": 35000.0,
                "reasoning": "Diagnosis matches appendicitis/appendectomy. Eligible for surgical intervention package.",
                "guidelines": [
                    "Attach ultrasound abdomen/pelvis report confirming appendicitis",
                    "Provide histopathological report of the removed appendix post-op",
                    "Attach pre-anesthetic clearance report"
                ]
            }

        # 3. Cholecystectomy Package Matcher
        if any(kw in diag_lower for kw in ["cholecystectomy", "cholecystitis", "gallstone"]):
            return {
                "eligible": True,
                "package_name": "Laparoscopic Cholecystectomy",
                "package_code": "SG022",
                "coverage_amount": 40000.0,
                "reasoning": "Diagnosis indicates gallstones or gallbladder inflammation. Covered for surgical removal.",
                "guidelines": [
                    "Attach abdominal ultrasound showing cholelithiasis or cholecystitis",
                    "Attach liver function test (LFT) report",
                    "Attach post-operative specimen biopsy report"
                ]
            }

        # 4. Angioplasty Package Matcher
        if any(kw in diag_lower for kw in ["angioplasty", "heart attack", "myocardial infarction", "cad"]):
            return {
                "eligible": True,
                "package_name": "Coronary Angioplasty with Single Drug-Eluting Stent",
                "package_code": "CR002",
                "coverage_amount": 120000.0,
                "reasoning": "Diagnosis indicates coronary artery disease or cardiac event. Covered for emergency angioplasty.",
                "guidelines": [
                    "Attach ECG indicating ischemic changes or infarction",
                    "Attach Coronary Angiography report and CD footage link",
                    "Provide cardiologist's recommendation letter"
                ]
            }

        # 5. Cataract Surgery Package Matcher
        if "cataract" in diag_lower:
            return {
                "eligible": True,
                "package_name": "Cataract Surgery with Foldable IOL",
                "package_code": "OP003",
                "coverage_amount": 12000.0,
                "reasoning": "Diagnosis matches cataract. Single eye cataract surgery covered.",
                "guidelines": [
                    "Attach slit-lamp examination findings",
                    "Provide biometry report for intraocular lens (IOL) power",
                    "Attach post-operative visual acuity assessment"
                ]
            }

        # 6. Complicated Diabetes Package Matcher
        if "diabetes" in diag_lower:
            hba1c_value = None
            for lab in labs:
                if "hba1c" in lab.test_name.lower():
                    hba1c_value = lab.value
                    break
            
            if hba1c_value is not None and hba1c_value > 8.0:
                return {
                    "eligible": True,
                    "package_name": "Management of Complicated Diabetes Mellitus",
                    "package_code": "MG004",
                    "coverage_amount": 15000.0,
                    "reasoning": f"Diagnosis matches 'Diabetes' and HbA1c lab result is {hba1c_value}%, which is above the complication threshold of 8.0%.",
                    "guidelines": [
                        "Attach latest HbA1c laboratory report",
                        "Include blood glucose monitoring logs",
                        "Document clinical signs of diabetic complication (e.g. nephropathy, neuropathy)"
                    ]
                }
            elif hba1c_value is not None:
                return {
                    "eligible": False,
                    "package_name": "Management of Complicated Diabetes Mellitus",
                    "package_code": "MG004",
                    "coverage_amount": 0.0,
                    "reasoning": f"Diagnosis matches 'Diabetes' but HbA1c lab result ({hba1c_value}%) is below the complication threshold (8.0%) required for PM-JAY package approval.",
                    "guidelines": [
                        "Patient may qualify for routine outpatient care, which is not covered under PM-JAY tertiary care hospitalization."
                    ]
                }
            else:
                return {
                    "eligible": True,
                    "package_name": "Standard Diabetes Care (Admitted)",
                    "package_code": "MG005",
                    "coverage_amount": 8000.0,
                    "reasoning": "Diagnosis matches 'Diabetes'. Eligible for standard inpatient diabetes care. Upload HbA1c labs to verify eligibility for the high-coverage complicated diabetes package.",
                    "guidelines": [
                        "Attach fasting/post-prandial blood sugar reports",
                        "Upload HbA1c report to verify if eligible for complicated care packages"
                    ]
                }

        # Fallback for unrecognized diagnoses
        return {
            "eligible": False,
            "package_name": "N/A",
            "package_code": "N/A",
            "coverage_amount": 0.0,
            "reasoning": f"The diagnosis '{diagnosis}' could not be matched with any standard covered PM-JAY tertiary care packages.",
            "guidelines": [
                "Verify if the condition is listed under secondary or tertiary care packages",
                "Consult the PM-JAY National Health Authority guidelines for updates"
            ]
        }
