from flask import Flask, request, jsonify
from consulta import buscar_localizacao, incluir_estoque
import traceback

app = Flask(__name__)

def build_response(text, end_session=True, session_attrs=None, reprompt=None):
    """
    Monta a resposta Alexa com SSML + sessionAttributes + reprompt.
    """
    resp = {
        "version": "1.0",
        "sessionAttributes": session_attrs or {},
        "response":{
            "outputSpeech": {"type": "SSML", "ssml": f"<speak>{text}</speak>"},
            "shouldEndSession": end_session
        }
    }

    if not end_session:
        resp["response"]["reprompt"] = {
            "outputSpeech": {"type": "SSML", "ssml": f"<speak>{reprompt or text}</speak>"}
        }

    return resp

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
    session_attrs = payload.get("session", {}).get("attributes", {}) or {}
    flow = session_attrs.get("flow") #estados: ASK_MATERIAL, ASK_QTD, ASK_SETOR, CONFIRM

    # Launch
    if r_type == 'LaunchRequest':
        session_attrs.update({"flow": "ASK_MATERIAL"})
        msg = "Olá! Para incluir no estoque, diga o nome do material."
        return jsonify(build_response(msg, end_session=False, session_attrs=session_attrs, reprompt="Diga o nome do material."))
    
    # Intent
    if r_type == 'IntentRequest':
        intent_name = payload['request']['intent']['name']

        if intent_name == 'ConsultaMaterialIntent':
            material = get_slot(payload, 'material')
            if not material:
                return jsonify(build_response("Não entendi o material. Pode repetir?", end_session=False,
                                              session_attrs=session_attrs, reprompt="Diga o nome do material para buscar."))
        
            try:
                resposta = buscar_localizacao(material)
                resposta += "<break time='0.5s'/> Deseja buscar outro material?"
                session_attrs.setdefault("flow", "ASK_MATERIAL")
                return jsonify(build_response(resposta, end_session=False, session_attrs=session_attrs,
                                              reprompt="Você deseja buscar outro material?"))
            
            except Exception:
                print(traceback.format_exc())
                return jsonify(build_response("Ocorreu um erro ao buscar o material.", end_session=False,
                                              session_attrs=session_attrs, reprompt="Quer tentar novamente?"))
            

            # Inclusão de estoque
        if intent_name == "IncluirEstoqueIntent":
            material    = get_slot(payload, 'material')
            quantidade  = get_slot(payload, 'quantidade')
            setor       = get_slot(payload, 'setor') 

            if material  : session_attrs["material"]   = material
            if quantidade: session_attrs["quantidade"] = quantidade
            if setor     : session_attrs["setor"]      = setor

            if not session_attrs.get("material"):
                session_attrs["flow"] = "ASK_MATERIAL"
                return jsonify(build_response("Informe o nome do material.", end_session=False,
                                              session_attrs=session_attrs, reprompt="Qual o material?"))
            
            if not session_attrs.get("quantidade"):
                session_attrs["flow"] = "ASK_QTD"
                return jsonify(build_response(f"Você disse{session_attrs['material']}.Qual é a quantidade?",
                                            end_session=False, session_attrs=session_attrs, reprompt="Qual é a quantidade?"))
            

            try:
                qtd = int(session_attrs["quantidade"])
                if qtd <= 0:
                    raise ValueError()
            except Exception:
                session_attrs.pop("quantidade", None)
                session_attrs["flow"] = "ASK_QTD"
                return jsonify(build_response("A quantidade deve ser um número maior que zero. Diga novamente.",
                                              end_session=False, session_attrs=session_attrs, reprompt="Qual é a quantidade?"))
            
            
            if not session_attrs.get("setor"):
                session_attrs["flow"] = "ASK_SETOR"
                return jsonify(build_response("Em qual setor deseja incluir?", end_session=False,
                                              session_attrs=session_attrs, reprompt="Diga o setor."))
            # confirmação final
            session_attrs["flow"] = "CONFIRM"
            frase = f"Confirmando: incluir {session_attrs['quantidade']} do material {session_attrs['material']} no setor {session_attrs['setor']}. Posso gravar?"
            return jsonify(build_response(frase, end_session=False, session_attrs=session_attrs, reprompt="Posso gravar? Diga sim ou não."))

        # Após pergunta finak
        if intent_name == 'AMAZON.YesIntent' and flow == "CONFIRM":
            material    =     session_attrs.get("material")
            quantidade  = int(session_attrs.get("quantidade"))
            setor       =     session_attrs.get("setor")

            try:
                novo_id = incluir_estoque(material, quantidade, setor, 
                                        user_id   = payload.get("session", {}).get("user", {}).get("userId"),
                                        device_id = payload.get("context", {}).get("System", {}).get("device", {}).get("deviceId"))
                
                session_attrs.clear()
                msg = f"Material {material} com quantidade {quantidade} incluído no setor {setor} com sucesso."
                return jsonify(build_response(msg, end_session=True, session_attrs=session_attrs))
            except Exception:
                print(traceback.format_exc())
                session_attrs.clear()
                return jsonify(build_response("Desculpe ocorreu um erro ao gravar os dados.", end_session=True))
        
        if intent_name == 'AMAZON.NoIntent' and flow in {"ASK_MATERIAL", "ASK_QTD", "ASK_SETOR", "CONFIRM"}:
            #volta pro começo do fluxo
            session_attrs = {"flow": "ASK_MATERIAL"}
            return jsonify(build_response("Sem problemas. Diga novamente o nome do material.", end_session=False,
                                        session_attrs=session_attrs, reprompt="Qual o material?"))
        
        # intents padrão
        if intent_name in ['AMAZON.CancelIntent', 'AMAZON.StopIntent']:
            return jsonify({
                "version": "1.0",
                "response":{
                    "outputSpeech": {"type": "PlainText", "text": "Ok, até a próxima!"},
                    "shouldEndSession": True
                }
            })
    

        return  jsonify(build_response("Desculpe, não entendi o pedido.", end_session=False,
                                    session_attrs=session_attrs, reprompt="Pode repetir?"))

    # Outros tipos
    return jsonify(build_response("Requisição não suportada.", end_session=True))

if __name__ == "__main__":
    app.run(port=5000, debug=True)