import html
import logging
import os
import random
import time
from datetime import datetime, timedelta, timezone
import requests
from supabase import create_client
from dotenv import load_dotenv

# Força o Python a ler o arquivo .env local. No Render, ele ignora isso.
load_dotenv(override=True)

# ---------------------------------------------------------------------------
# 1. CONFIGURAÇÕES GERAIS
# ---------------------------------------------------------------------------
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]     
ADMIN_CHAT_ID = os.environ["ADMIN_CHAT_ID"]           

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("bot-fila-ofertas")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ---------------------------------------------------------------------------
# 2. FUNÇÕES AUXILIARES
# ---------------------------------------------------------------------------
def notificar_admin(mensagem: str) -> None:
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": ADMIN_CHAT_ID, "text": f"⚠️ ERRO NO BOT: {mensagem}"},
            timeout=10,
        )
    except Exception:
        pass 

def brl(valor: float) -> str:
    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# ---------------------------------------------------------------------------
# 3. LÓGICA PRINCIPAL
# ---------------------------------------------------------------------------
def processar_fila() -> bool:
    """Retorna True se postou uma oferta, False se não havia nada ou deu erro."""
    log.info("Checando nova oferta na fila...")
    try:
        res = supabase.table("ofertas_fila").select("*").eq("enviado", False).order("created_at", desc=False).limit(1).execute()
        
        if not res.data:
            return False

        item = res.data[0]
        item_id = item["id"]
        titulo = item["titulo"]
        preco_hoje = float(item["preco_hoje"])
        preco_original = float(item["preco_original"]) if item.get("preco_original") else None
        preco_cupom = float(item["preco_cupom"]) if item.get("preco_cupom") else None
        link = item["link_afiliado"]
        cupom = item.get("cupom")
        imagem_url = item.get("imagem_url")

        # SE PREENCHEU O PREÇO ORIGINAL: Usa o layout de promoção normal
        # (Não depende mais de matemática, basta o campo não estar vazio)
        if preco_original:
            cabecalho = f"<b>{html.escape(titulo)}</b>\n\n"
            texto_base = f"De: R$ {brl(preco_original)} | Por: R$ {brl(preco_hoje)} 💵\n"
            
        # SE NÃO PREENCHEU O PREÇO ORIGINAL: Usa o layout "Achado Pokémon"
        else:
            cabecalho = f"🔥 <b>ACHADO POKÉMON</b>\n\n📦 <b>{html.escape(titulo)}</b>\n\n"
            texto_base = f"💵 Apenas: R$ {brl(preco_hoje)}\n"

        # LÓGICA DO CUPOM NA MESMA LINHA
        texto_cupom = ""
        if cupom:
            if preco_cupom:
                texto_cupom = f"🎟️ Com cupom fica: R$ {brl(preco_cupom)} (Use: {html.escape(cupom)})\n"
            else:
                texto_cupom = f"🎟️ Use o cupom: {html.escape(cupom)}\n"

        mensagem = (
            f"{cabecalho}"
            f"{texto_base}"
            f"{texto_cupom}\n"
            f"🔗 Compre aqui:\n"
            f"{html.escape(link, quote=True)}" 
        )

        # Lógica de fallback da imagem
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
            log.info("✅ Enviado com sucesso: %s", titulo)
            return True
        else:
            notificar_admin(f"Falha no Telegram. Erro: {resp.text}")
            return False

    except Exception as e:
        notificar_admin(f"Erro no banco de dados: {e}")
        return False

# ---------------------------------------------------------------------------
# 4. O CÉREBRO "HUMANO" DO BOT COM LIMITE DIÁRIO
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    log.info("🤖 Bot Iniciado! Carregando regras de horários e limites...")
    
    MAX_POSTS_PER_DAY = int(os.environ.get("MAX_POSTS_PER_DAY", "6"))
    
    fuso_br = timezone(timedelta(hours=-3))
    
    posts_hoje = 0
    dia_atual = datetime.now(fuso_br).date()
    
    while True:
        agora = datetime.now(fuso_br)
        hora = agora.hour
        hoje = agora.date()
        
        if hoje != dia_atual:
            dia_atual = hoje
            posts_hoje = 0
            log.info("🌅 Novo dia! Contador de postagens zerado.")
        
        if hora >= 22 or hora < 7:
            log.info("⏰ Fora do horário comercial. Dormindo...")
            time.sleep(300) 
            continue
            
        if posts_hoje >= MAX_POSTS_PER_DAY:
            log.info(f"🛑 Limite de {MAX_POSTS_PER_DAY} postagens atingido por hoje. Pausando até amanhã...")
            time.sleep(3600) 
            continue
            
        postou_algo = processar_fila()
        
        if postou_algo:
            posts_hoje += 1
            log.info(f"📊 Progresso do dia: {posts_hoje}/{MAX_POSTS_PER_DAY} postagens realizadas.")
            
            if (11 <= hora <= 14) or (18 <= hora <= 21):
                espera_minutos = random.randint(120, 150)
                log.info(f"🔥 Horário de pico! Próxima tentativa em {espera_minutos} minutos.")
            else:
                espera_minutos = random.randint(150, 210)
                log.info(f"☕ Horário normal. Próxima tentativa em {espera_minutos} minutos.")
                
            time.sleep(espera_minutos * 60)
            
        else:
            time.sleep(600)