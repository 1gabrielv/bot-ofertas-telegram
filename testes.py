import os
import html
import requests
from supabase import create_client
from dotenv import load_dotenv

load_dotenv(override=True)
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def brl(valor: float) -> str:
    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def testar_bot():
    print("Buscando uma oferta pendente no banco de dados...")
    
    res = supabase.table("ofertas_fila").select("*").eq("enviado", False).order("created_at", desc=False).limit(1).execute()
    
    if not res.data:
        print("Nenhuma oferta com enviado=False encontrada na fila.")
        return

    item = res.data[0]
    titulo = item["titulo"]
    preco_hoje = float(item["preco_hoje"])
    preco_original = float(item["preco_original"]) if item.get("preco_original") else None
    link = item["link_afiliado"]
    cupom = item.get("cupom")
    imagem_url = item.get("imagem_url")

    if not imagem_url:
        print("⚠️ AVISO: O item encontrado não possui 'imagem_url' preenchida no Supabase.")
        return

    texto_preco = ""
    if preco_original and preco_original > preco_hoje:
        texto_preco = f"De R$ {brl(preco_original)} Por R$ {brl(preco_hoje)} 💵\n"
    else:
        texto_preco = f"Por R$ {brl(preco_hoje)} 💵\n"

    texto_cupom = f"Use o cupom: {html.escape(cupom)} 📌\n" if cupom else ""

    mensagem = (
        f"<b>{html.escape(titulo)}</b>\n\n"
        f"{texto_preco}"
        f"{texto_cupom}\n"
        f"Loja no Mercado Livre:\n"
        f"{html.escape(link, quote=True)}" 
    )

    print("\nEnviando foto com legenda para o Telegram...")

    # Disparo usando a rota de foto em vez de mensagem de texto
    resp = requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto",
        json={
            "chat_id": TELEGRAM_CHAT_ID, 
            "photo": imagem_url,
            "caption": mensagem,
            "parse_mode": "HTML"
        },
        timeout=15,
    )

    if resp.status_code == 200:
        print("✅ Sucesso! A foto em tamanho grande com a legenda foi enviada ao Telegram.")
    else:
        print(f"❌ Erro da API do Telegram: {resp.text}")

if __name__ == "__main__":
    testar_bot()