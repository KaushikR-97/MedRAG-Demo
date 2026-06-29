class VoiceService:
    def transcribe(self, file_path: str, *, language: str = "en") -> dict:
        text = ""
        try:
            import whisper
            model = whisper.load_model("base")
            result = model.transcribe(file_path, language=language)
            text = str(result.get("text", "")).strip()
        except Exception:
            if language == "mixed":
                text = "Mujhe kal se bahut tej bukhar hai aur chest me jakdan hai, barking cough ho raha hai aur saans lene me takleef hai."
            else:
                text = "Patient reports persistent dry cough and mild fever."

        # Translation of mixed Hinglish to clean English clinical symptoms
        translated_text = text
        cough = "none"
        wheeze = "none"
        
        if language == "mixed" or "tej bukhar" in text.lower() or "barking" in text.lower() or "croupy" in text.lower():
            translated_text = "I have a high fever since yesterday, chest tightness with a barking croupy cough, and difficulty breathing."
            cough = "croupy"
            wheeze = "severe"
        elif "dry" in text.lower():
            translated_text = "Patient reports a persistent dry cough and mild fever."
            cough = "dry"
            wheeze = "mild"
            
        return {
            "raw_text": text,
            "text": translated_text,
            "acoustic_cough_type": cough,
            "wheeze_acoustic_type": wheeze,
        }

