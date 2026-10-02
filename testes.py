import html
import logging
import os
import requests
from supabase import create_client
from dotenv import load_dotenv

load_dotenv(override=True)

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]     

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("bot-teste")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def brl(valor: float) -> str:
    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def testar_envio():
    log.info("Buscando 1 oferta na fila para teste manual...")
    try:
        res = supabase.table("ofertas_fila").select("*").eq("enviado", False).order("created_at", desc=False).limit(1).execute()
        
        if not res.data:
            log.info("Nenhuma oferta pendente na fila.")
            return

        item = res.data[0]
        item_id = item["id"]
        titulo = item["titulo"]
        preco_hoje = float(item["preco_hoje"])
        preco_original = float(item["preco_original"]) if item.get("preco_original") else None
        preco_cupom = float(item["preco_cupom"]) if item.get("preco_cupom") else None
        link = item["link_afiliado"]
        cupom = item.get("cupom")
        imagem_url = item.get("imagem_url")

        if preco_original and preco_original > preco_hoje:
            cabecalho = f"<b>{html.escape(titulo)}</b>\n\n"
            texto_base = f"De: R$ {brl(preco_original)} | Por: R$ {brl(preco_hoje)} 💵\n"
        else:
            cabecalho = f"🔥 <b>ACHADO POKÉMON</b>\n\n📦 <b>{html.escape(titulo)}</b>\n\n"
            texto_base = f"💵 Apenas: R$ {brl(preco_hoje)}\n"

        texto_cupom = ""
        if cupom:
            if preco_cupom:
                texto_cupom = f"🎟️️ Com cupom fica: R$ {brl(preco_cupom)} (Use: {html.escape(cupom)})\n"
            else:
                texto_cupom = f"🎟️ Use o cupom: {html.escape(cupom)}\n"

        mensagem = (
            f"{cabecalho}"
            f"{texto_base}"
            f"{texto_cupom}\n"
            f"🔗 Compre aqui:\n"
            f"{html.escape(link, quote=True)}" 
        )

        if imagem_url:
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
        else:
            resp = requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                json={
                    "chat_id": TELEGRAM_CHAT_ID, 
                    "text": mensagem, 
                    "parse_mode": "HTML",
                    "link_preview_options": {
                        "is_disabled": False,
                        "prefer_large_media": True,
                        "show_above_text": True
                    }
                },
                timeout=15,
            )

        if resp.status_code == 200:
            supabase.table("ofertas_fila").update({"enviado": True}).eq("id", item_id).execute()
            log.info("✅ Teste enviado com sucesso: %s", titulo)
        else:
            log.error("❌ Falha no Telegram. Erro: %s", resp.text)

    except Exception as e:
        log.error("Erro durante o teste: %s", e)

if __name__ == "__main__":
    testar_envio()