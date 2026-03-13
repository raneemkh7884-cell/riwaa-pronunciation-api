from flask import Flask, request, jsonify
import azure.cognitiveservices.speech as speechsdk
import json
import os
import uuid

app = Flask(__name__)

SPEECH_KEY = os.environ.get("SPEECH_KEY")
REGION = os.environ.get("REGION")

@app.route("/check-pronunciation", methods=["POST"])
def check_pronunciation():
    temp_filename = None

    try:
        if not SPEECH_KEY or not REGION:
            return jsonify({
                "success": False,
                "error": "Missing SPEECH_KEY or REGION in environment variables"
            }), 500

        reference_text = request.form.get("reference_text")
        audio_file = request.files.get("audio")

        if not reference_text:
            return jsonify({"success": False, "error": "reference_text is required"}), 400

        if not audio_file:
            return jsonify({"success": False, "error": "audio file is required"}), 400

        temp_filename = f"temp_{uuid.uuid4().hex}.wav"
        audio_file.save(temp_filename)

        speech_config = speechsdk.SpeechConfig(subscription=SPEECH_KEY, region=REGION)
        speech_config.speech_recognition_language = "ar-SA"

        audio_config = speechsdk.audio.AudioConfig(filename=temp_filename)

        speech_recognizer = speechsdk.SpeechRecognizer(
            speech_config=speech_config,
            audio_config=audio_config
        )

        pron_config = speechsdk.PronunciationAssessmentConfig(
            reference_text=reference_text,
            grading_system=speechsdk.PronunciationAssessmentGradingSystem.HundredMark,
            granularity=speechsdk.PronunciationAssessmentGranularity.Phoneme,
            enable_miscue=True
        )

        pron_config.apply_to(speech_recognizer)

        result = speech_recognizer.recognize_once()

        if result.reason == speechsdk.ResultReason.NoMatch:
            return jsonify({
                "success": False,
                "error": "No speech recognized"
            }), 400

        if result.reason == speechsdk.ResultReason.Canceled:
            cancellation = speechsdk.CancellationDetails(result)
            return jsonify({
                "success": False,
                "error": "Recognition canceled",
                "details": cancellation.error_details
            }), 500

        json_result = result.properties.get(
            speechsdk.PropertyId.SpeechServiceResponse_JsonResult
        )

        if not json_result:
            return jsonify({
                "success": False,
                "error": "No JSON result returned"
            }), 500

        data = json.loads(json_result)
        nbest = data["NBest"][0]
        pa = nbest.get("PronunciationAssessment", {})
        words = nbest.get("Words", [])

        phoneme_scores = []
        all_good = True
        has_any_phoneme = False

        for word in words:
            phonemes = word.get("Phonemes", [])
            for p in phonemes:
                has_any_phoneme = True

                phoneme = p.get("Phoneme", "")
                score = p.get("PronunciationAssessment", {}).get("AccuracyScore", 0)

                phoneme_scores.append({
                    "phoneme": phoneme,
                    "score": score
                })

                if score < 80:
                    all_good = False

                recognized_text = result.text.strip() if result.text else ""
                is_correct = has_any_phoneme and all_good

        is_correct = has_any_phoneme and all_good

        return jsonify({
            "success": True,
            "recognized_text": recognized_text,
            "accuracy": pa.get("AccuracyScore", 0),
            "fluency": pa.get("FluencyScore", 0),
            "completeness": pa.get("CompletenessScore", 0),
            "pron_score": pa.get("PronScore", 0),
            "phonemes": phoneme_scores,
            "is_correct": is_correct
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

    finally:
        if temp_filename and os.path.exists(temp_filename):
            os.remove(temp_filename)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)