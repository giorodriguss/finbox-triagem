import os
from flask import Flask, render_template, request, session, redirect, url_for
import google.generativeai as genai
import json
import PyPDF2
from dotenv import load_dotenv

# Carrega variáveis de ambiente
load_dotenv()

app = Flask(__name__)

# Chave de sessão obtida via variável de ambiente
# Mantém segurança em produção e simplicidade em desenvolvimento local
app.secret_key = os.getenv("FLASK_SECRET_KEY", "chave-padrao-dev")

# Configuração da API externa via variável de ambiente
MINHA_CHAVE = os.getenv("GOOGLE_API_KEY")
genai.configure(api_key=MINHA_CHAVE)

def extract_text(file, file_ext):
    """
    Extrai texto de arquivos enviados pelo usuário.
    Atualmente suporta PDF e arquivos de texto simples.
    """
    try:
        if file_ext == '.pdf':
            pdf_reader = PyPDF2.PdfReader(file)
            text = ""
            for page in pdf_reader.pages:
                # Evita None em páginas sem texto extraível
                text += page.extract_text() or ""
            return text
        else: 
            return file.read().decode('utf-8')
    except Exception as e:
        # Retorna mensagem controlada para evitar quebra do fluxo
        return f"Erro ao ler arquivo: {e}"

def analyze_email(email_content):
    """
    Responsável por enviar o conteúdo do email para análise semântica
    e retornar uma resposta estruturada em JSON.
    """
    model = genai.GenerativeModel('gemini-flash-latest')
    
    # Prompt estruturado para garantir respostas previsíveis
    # e facilmente consumidas pelo frontend
    prompt = f"""
    Analise este email recebido:
    "{email_content}"

    --- REGRAS DE RESPOSTA ---
    1. PRODUTIVO (Problemas, Dúvidas, Solicitações): Escreva uma resposta formal e resolutiva.
    2. SOCIAL (Elogios, Felicitações, Bom dia): Escreva uma resposta curta, educada e empática.
    3. AUTOMÁTICO (Propagandas, spam, No-reply, LinkedIn, Notificações): A resposta sugerida deve ser APENAS: "Sem resposta necessária. Recomendação: Arquivar."
    --------------------------

    Tarefas:
    1. Classifique: 'Produtivo' ou 'Improdutivo'.
    2. Sentimento: 'Feliz', 'Neutro' ou 'Irritado'.
    3. Urgência: 'Alta', 'Média' ou 'Baixa'.
    4. Extração: Liste dados chave com um breve contexto (CPF, Valores, Datas).
    5. Resumo: Uma frase curta.

    Responda EXATAMENTE neste JSON:
    {{
        "classificacao": "Produtivo/Improdutivo",
        "sentimento": "Feliz/Neutro/Irritado",
        "urgencia": "Alta/Média/Baixa",
        "dados_chave": ["Dado 1", "Dado 2"],
        "resumo": "...",
        "resposta_sugerida": "..."
    }}
    """
    
    try:
        response = model.generate_content(prompt)

        # Remove possíveis marcações de bloco de código retornadas pelo modelo
        texto_limpo = response.text.replace('```json', '').replace('```', '').strip()
        return texto_limpo
        
    except Exception as e:
        erro_str = str(e)

        # Tratamento específico para limite de cota da API
        # Mantém a aplicação funcional e comunica claramente o problema
        if "429" in erro_str or "Quota" in erro_str:
            return json.dumps({
                "classificacao": "COTA_EXCEDIDA",
                "sentimento": "Neutro",
                "urgencia": "Baixa",
                "dados_chave": [],
                "resumo": "Limite diário da API atingido.",
                "resposta_sugerida": "O sistema atingiu o limite de requisições gratuitas do Google Gemini hoje. Tente novamente amanhã."
            })
        else:
            # Log simples para depuração
            print("\n🔴 ERRO:", e)
            return json.dumps({
                "classificacao": "Erro",
                "sentimento": "Neutro",
                "urgencia": "Baixa", 
                "dados_chave": [],
                "resumo": "Erro técnico.", 
                "resposta_sugerida": "Houve um erro de conexão."
            })

@app.route('/', methods=['GET', 'POST'])
def index():
    result = None

    # Inicializa histórico na sessão, caso ainda não exista
    if 'history' not in session:
        session['history'] = []

    if request.method == 'POST':
        email_text = request.form.get('email_text', "")
        file = request.files.get('email_file')
        
        # Prioriza texto extraído de arquivo, se enviado
        if file and file.filename != '':
            ext = os.path.splitext(file.filename)[1].lower()
            text_from_file = extract_text(file, ext)
            if text_from_file:
                email_text = text_from_file
        
        if email_text:
            ai_response_json = analyze_email(email_text)
            try:
                result = json.loads(ai_response_json)
                result['original_text'] = email_text
                
                # Salva apenas respostas válidas no histórico
                if result.get('classificacao') != 'COTA_EXCEDIDA' and result.get('classificacao') != 'Erro':

                    session['history'].insert(0, result)
                    
                    # Mantém apenas os últimos 3 registros
                    session['history'] = session['history'][:3]

                    session.modified = True 
            except:
                result = None

    return render_template('index.html', result=result, history=session['history'])

@app.route('/limpar')
def limpar_historico():
    """
    Limpa o histórico armazenado na sessão do usuário.
    """
    session.pop('history', None)
    return redirect(url_for('index'))

if __name__ == '__main__':
    # Debug ativado apenas para ambiente de desenvolvimento
    app.run(debug=True)