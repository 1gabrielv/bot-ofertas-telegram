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
        link = item["link_afiliado"]
        cupom = item.get("cupom")
        imagem_url = item.get("imagem_url") # <-- Variável da imagem puxada do banco

        texto_preco = ""
        if preco_original and preco_original > preco_hoje:
            texto_preco = f"De R$ {brl(preco_original)} Por R$ {brl(preco_hoje)} 💵\n"
        else:
            texto_preco = f"Por R$ {brl(preco_hoje)} 💵\n"

        texto_cupom = f"Use o cupom: {html.escape(cupom)} 📌\n" if cupom else ""

        # Título colocado em negrito (<b>) para dar destaque na legenda
        mensagem = (
            f"<b>{html.escape(titulo)}</b>\n\n"
            f"{texto_preco}"
            f"{texto_cupom}\n"
            f"Loja no Mercado Livre:\n"
            f"{html.escape(link, quote=True)}" 
        )

        # Lógica de fallback: Tenta foto primeiro, se não tiver, manda texto
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
    
    # Puxa o limite do .env (se não achar, usa 8 como padrão)
    MAX_POSTS_PER_DAY = int(os.environ.get("MAX_POSTS_PER_DAY", "8"))
    
    # Define o fuso horário de Brasília (UTC-3)
    fuso_br = timezone(timedelta(hours=-3))
    
    # Contadores diários
    posts_hoje = 0
    dia_atual = datetime.now(fuso_br).date()
    
    while True:
        agora = datetime.now(fuso_br)
        hora = agora.hour
        hoje = agora.date()
        
        # REGRA 1: Virada do dia (Reseta o contador de postagens)
        if hoje != dia_atual:
            dia_atual = hoje
            posts_hoje = 0
            log.info("🌅 Novo dia! Contador de postagens zerado.")
        
        # REGRA 2: Madrugada (22h00 até 07h59) -> O bot dorme
        if hora >= 22 or hora < 7:
            log.info("⏰ Fora do horário comercial. Dormindo...")
            time.sleep(3600) # Dorme 1 hora e checa o relógio de novo
            continue
            
        # REGRA 3: Limite de postagens diárias
        if posts_hoje >= MAX_POSTS_PER_DAY:
            log.info(f"🛑 Limite de {MAX_POSTS_PER_DAY} postagens atingido por hoje. Pausando até amanhã...")
            time.sleep(3600) # Checa de hora em hora até virar o dia
            continue
            
        # REGRA 4: Horário comercial e dentro do limite -> Tenta postar
        postou_algo = processar_fila()
        
        # REGRA 5: Calculador de ritmo humano
        if postou_algo:
            posts_hoje += 1
            log.info(f"📊 Progresso do dia: {posts_hoje}/{MAX_POSTS_PER_DAY} postagens realizadas.")
            
            # Horários de Pico (11h-14h e 18h-21h)
            if (11 <= hora <= 14) or (18 <= hora <= 21):
                espera_minutos = random.randint(45, 75)
                log.info(f"🔥 Horário de pico! Próxima tentativa em {espera_minutos} minutos.")
            # Horários Normais (08h-10h e 15h-17h)
            else:
                espera_minutos = random.randint(60, 120)
                log.info(f"☕ Horário normal. Próxima tentativa em {espera_minutos} minutos.")
                
            time.sleep(espera_minutos * 60)
            
        else:
            # Se não postou nada (banco vazio), espera 10 minutos e checa o banco de novo
            time.sleep(600)