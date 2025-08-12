from flask import Flask, request, jsonify
from consulta import buscar_localizacao, incluir_estoque
import traceback

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

    # Launch
    if r_type == 'LaunchRequest':
        msg = "Olá! Para incluir no estoque, diga o nome do material."
        return jsonify(build_response(msg, end_session=False))
    
    # Intent
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
            

            # Inclusão de estoque
        if intent_name  in ("IncludeEstoqueIntent", "IncluirEstoqueIntent"):
            dialog_state = payload['request'].get('dialogState')
            confirmation = (intent_obj.get("confirmationStatus") or "NONE").upper()
            slots        =  intent_obj.get("slots", {}) or {}

            def has(slot):
                return slots.get(slot, {}).get("value") not in (None, "")
                
            # 1) Se já está tudo confirmado e preenchido, FINALIZA (grava e responde)
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
                    return jsonify(build_response(msg, end_session=True))  # <<< sem diretivas aqui
                except Exception:
                    print(traceback.format_exc())
                    return jsonify(build_response("Desculpe, ocorreu um erro ao gravar os dados.", end_session=True))

            # 2) Se o usuário negou na confirmação final do intent
            if confirmation == "DENIED":
                return jsonify(build_response("Ok, operação cancelada."))

            # 3) Caso contrário, ainda está no fluxo -> delega para Alexa continuar
            if dialog_state != "COMPLETED":
                return jsonify(delegate(intent_obj))

            # 4) (fallback) COMPLETED sem confirmação
            return jsonify(build_response("Ok, operação cancelada."))

        # Intents padrão
        if intent_name in ("AMAZON.CancelIntent", "AMAZON.StopIntent"):
            return jsonify({
                "version": "1.0",
                "response": {
                    "outputSpeech": {"type": "PlainText", "text": "Ok, até a próxima!"},
                    "shouldEndSession": True
                }
            })

        # Fallback
        return jsonify(build_response("Desculpe, não entendi o pedido.", end_session=False))

    # SessionEnded: não fale nada; só ack e log se quiser
    if r_type == "SessionEndedRequest":
        # print("SessionEnded:", payload["request"].get("reason"), payload["request"].get("error"))
        return jsonify({"version": "1.0"}), 200

    # Outros tipos
    return jsonify(build_response("Requisição não suportada.", end_session=True))

if __name__ == "__main__":
    app.run(port=5000, debug=True)