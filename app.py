from flask import Flask, request, jsonify
from consulta import buscar_localizacao, incluir_estoque
import traceback
import os 
import logging
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

def build_response(text, end_session=True):
    return{
        "version" : "1.0",
        "response": {
            "outputSpeech": {"type": "SSML", "ssml": f"<speak>{text}</speak>"},
            "shouldEndSession": end_session
        }
    }

def delegate(updated_intent=None):
    resp = {
        "version": "1.0",
        "response": {
            "directives": [{"type": "Dialog.Delegate"}],
            "shouldEndSession": False
        }
    }
    
    if updated_intent:
        resp["response"]["directives"][0]["updatedIntent"] = updated_intent
    return resp

def get_slot(payload, name):
    try:
        return payload["request"]["intent"]["slots"].get(name, {}).get("value")
    except Exception:
        return None
    
@app.route('/health', methods=['GET'])
def health_check():
    return 'OK', 200

@app.route('/alexa', methods=['POST'])
def alexa_webhook():
    payload = request.get_json(force=True, silent=True)
    if not payload or 'request' not in payload:
        return jsonify(build_response("Requisição inválida")), 400
    
    r_type = payload['request']['type']

    if r_type == 'LaunchRequest':
        msg = "Olá! Para incluir no estoque, diga o nome do item"
        return jsonify(build_response(msg, end_session=False))

    if r_type == 'IntentRequest':
        intent_obj  = payload["request"].get("intent", {}) or {}
        intent_name = intent_obj.get("name", "")

        if intent_name == 'ConsultaMaterialIntent':
            material = get_slot(payload, 'material')

            if not material:
                return jsonify(build_response("Não entendi o material. Pode repetir?", end_session=False))
        
            try:
                resposta = buscar_localizacao(material)
                resposta += "<break time='0.5s'/> Deseja buscar outro material?"
                return jsonify(build_response(resposta, end_session=False))
            
            except Exception:
                print(traceback.format_exc())
                return jsonify(build_response("Ocorreu um erro ao buscar o material.", end_session=False))
            
        if intent_name  in ("IncludeEstoqueIntent", "IncluirEstoqueIntent"):
            dialog_state = payload['request'].get('dialogState')
            confirmation = (intent_obj.get("confirmationStatus") or "NONE").upper()
            slots        =  intent_obj.get("slots", {}) or {}

            def has(slot):
                return slots.get(slot, {}).get("value") not in (None, "")
                
            if confirmation == "CONFIRMED" and has("material") and has("quantidade") and has("setor"):
                try:
                    material   = slots["material"]["value"]
                    quantidade = int(slots["quantidade"]["value"])
                    setor      = int(slots["setor"]["value"])
                except Exception:
                    return jsonify(build_response("Valores inválidos informados. Tente novamente.", end_session=True))

                try:
                    incluir_estoque(material, quantidade, setor)
                    msg = f"Material {material} com quantidade {quantidade} incluído no setor {setor} com sucesso."
                    return jsonify(build_response(msg, end_session=True)) 
                except Exception:
                    print(traceback.format_exc())
                    return jsonify(build_response("Desculpe, ocorreu um erro ao gravar os dados.", end_session=True))

            if confirmation == "DENIED":
                return jsonify(build_response("Ok, operação cancelada."))

            if dialog_state != "COMPLETED":
                return jsonify(delegate(intent_obj))

            return jsonify(build_response("Ok, operação cancelada."))

        if intent_name in ("AMAZON.CancelIntent", "AMAZON.StopIntent"):
            return jsonify({
                "version": "1.0",
                "response": {
                    "outputSpeech": {"type": "PlainText", "text": "Ok, até a próxima!"},
                    "shouldEndSession": True
                }
            })

        return jsonify(build_response("Desculpe, não entendi o pedido.", end_session=False))

    if r_type == "SessionEndedRequest":
        return jsonify({"version": "1.0"}), 200

    return jsonify(build_response("Requisição não suportada.", end_session=True))

def _configure_logging():
    debug_flag = _is_debug()
    if debug_flag:
        app.logger.setLevel(logging.DEBUG)
        return
    os.makedirs("logs", exist_ok=True)
    handler = RotatingFileHandler("logs/app.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    handler.setLevel(logging.INFO)
    app.logger.addHandler(handler)
    app.logger.setLevel(logging.INFO)

def _is_debug() -> bool:
    return str(os.getenv("DEBUG", "0")).lower() in ("1", "true", "yes", "on")

if __name__ == "__main__":
    _configure_logging()

    HOST = os.getenv("HOST", "0.0.0.0")
    PORT = int(os.getenv("PORT", "5000"))

    if _is_debug():
        app.run(host=HOST, port=PORT, debug=True)
    else:
        from waitress import serve
        THREADS          = int(os.getenv("THREADS", "4"))
        CONNECTION_LIMIT = int(os.getenv("CONNECTION_LIMIT", "100"))
        CHANNEL_TIMEOUT  = int(os.getenv("CHANNEL_TIMEOUT", "30"))

        app.logger.info("Iniciando Waitress em %s:%s (threads=%s, conn_limit=%s, timeout=%ss)",
                        HOST, PORT, THREADS, CONNECTION_LIMIT, CHANNEL_TIMEOUT)

        serve(
            app,
            host=HOST,
            port=PORT,
            threads=THREADS,
            connection_limit=CONNECTION_LIMIT,
            channel_timeout=CHANNEL_TIMEOUT,
            ident="alexa-estoque"
        )