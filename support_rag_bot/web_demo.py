from __future__ import annotations

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from support_rag_bot.config import get_settings
from support_rag_bot.services.crm_assist_service import CRMAssistService
from support_rag_bot.services.gemini_service import GeminiService
from support_rag_bot.services.rag_service import RAGService
from support_rag_bot.services.storage import KnowledgeBaseStore


class AssistRequest(BaseModel):
    client_message: str = Field(min_length=2, max_length=3500)
    manager_context: str = Field(default="", max_length=2000)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    store = KnowledgeBaseStore(settings.db_path)
    gemini = GeminiService(
        api_key=settings.gemini_api_key,
        generation_model=settings.gemini_generation_model,
        embedding_model=settings.gemini_embedding_model,
    )
    rag_service = RAGService(store=store, gemini=gemini, settings=settings)
    await rag_service.bootstrap()

    app.state.crm_assist = CRMAssistService(store=store, gemini=gemini, settings=settings)
    yield


app = FastAPI(
    title="AmoCRM AI Copilot Demo",
    description="RAG prototype: client reply + private upsell hint for a manager.",
    lifespan=lifespan,
)


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    return DEMO_HTML


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/assist")
async def assist(payload: AssistRequest) -> dict:
    service: CRMAssistService = app.state.crm_assist
    try:
        result = await service.assist(
            client_message=payload.client_message,
            manager_context=payload.manager_context,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI provider error: {type(exc).__name__}") from exc

    cited = set(result.citation_ids)
    sources = [
        {
            "id": hit.document.doc_id,
            "title": hit.document.title,
            "section": hit.document.section,
            "url": hit.document.url,
            "score": round(hit.score, 4),
        }
        for hit in result.hits
        if hit.document.doc_id in cited
    ]

    return {
        "client_reply": result.client_reply,
        "manager_hint": result.manager_hint,
        "upsell_product": result.upsell_product,
        "confidence": round(result.confidence, 3),
        "sources": sources,
    }


DEMO_HTML = """
<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AmoCRM AI Copilot Demo</title>
  <style>
    :root {
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: #172033;
      background: #f4f6fb;
    }
    * { box-sizing: border-box; }
    body { margin: 0; min-height: 100vh; background: linear-gradient(135deg, #f8faff, #eef3ff 55%, #f7f3ff); }
    .shell { max-width: 1180px; margin: 0 auto; padding: 38px 20px 56px; }
    .top { display: flex; justify-content: space-between; gap: 20px; align-items: end; margin-bottom: 24px; }
    .eyebrow { font-size: 12px; font-weight: 800; letter-spacing: .12em; text-transform: uppercase; color: #6d55d7; }
    h1 { margin: 8px 0 6px; font-size: clamp(30px, 5vw, 48px); letter-spacing: -.04em; }
    .sub { color: #667085; max-width: 720px; line-height: 1.55; }
    .badge { background: #e9f8ef; color: #18794e; border: 1px solid #bce8ce; padding: 8px 12px; border-radius: 999px; font-size: 13px; font-weight: 700; white-space: nowrap; }
    .grid { display: grid; grid-template-columns: 1.05fr .95fr; gap: 18px; }
    .card { background: rgba(255,255,255,.92); border: 1px solid #e2e8f0; border-radius: 20px; box-shadow: 0 18px 45px rgba(30, 41, 59, .08); }
    .pane { padding: 22px; }
    .title { font-size: 14px; font-weight: 800; margin-bottom: 12px; }
    label { display: block; font-size: 13px; font-weight: 700; margin: 18px 0 8px; color: #475467; }
    textarea { width: 100%; resize: vertical; border: 1px solid #d7deea; border-radius: 14px; padding: 14px; font: inherit; line-height: 1.45; background: #fbfcff; outline: none; }
    textarea:focus { border-color: #8875e6; box-shadow: 0 0 0 3px rgba(136,117,230,.13); }
    #message { min-height: 150px; }
    #context { min-height: 86px; }
    .samples { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 12px; }
    .sample { border: 1px solid #ddd8fa; background: #f7f5ff; color: #5c48c7; border-radius: 999px; padding: 8px 11px; cursor: pointer; font-size: 12px; }
    .run { width: 100%; margin-top: 18px; border: 0; border-radius: 14px; padding: 13px 16px; font: inherit; font-weight: 800; color: white; background: linear-gradient(135deg,#6f5be5,#4f7de8); cursor: pointer; }
    .run:disabled { opacity: .6; cursor: wait; }
    .output { padding: 18px; border-radius: 16px; margin-bottom: 14px; border: 1px solid #e4e7ec; background: #fff; min-height: 128px; }
    .output.manager { background: #fffaf0; border-color: #f4dfad; }
    .output h2 { font-size: 13px; margin: 0 0 10px; text-transform: uppercase; letter-spacing: .06em; color: #667085; }
    .text { white-space: pre-wrap; line-height: 1.55; }
    .meta { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 12px; }
    .chip { border-radius: 999px; padding: 6px 9px; font-size: 12px; background: #f2f4f7; color: #475467; }
    .source { display: block; margin-top: 7px; color: #5d4fc5; text-decoration: none; font-size: 13px; }
    .muted { color: #98a2b3; }
    .error { color: #b42318; }
    @media (max-width: 820px) { .grid { grid-template-columns: 1fr; } .top { align-items: start; flex-direction: column; } }
  </style>
</head>
<body>
  <main class="shell">
    <div class="top">
      <div>
        <div class="eyebrow">AmoCRM · AI Copilot prototype</div>
        <h1>Ответ клиенту + подсказка менеджеру</h1>
        <div class="sub">Сообщение клиента сверяется с короткой базой знаний. Клиентский ответ и внутренняя рекомендация разделены, а допродажа появляется только когда она подтверждается потребностью и KB.</div>
      </div>
      <div class="badge">RAG grounded</div>
    </div>

    <section class="grid">
      <div class="card pane">
        <div class="title">Диалог менеджера</div>
        <label for="message">Последнее сообщение клиента</label>
        <textarea id="message">У нас Starter, но мне нужен экспорт таблицы в CSV. Где его включить?</textarea>

        <label for="context">Контекст из карточки AmoCRM (необязательно)</label>
        <textarea id="context">Текущий тариф: Starter. Клиент рассматривает расширение возможностей команды.</textarea>

        <div class="samples">
          <button class="sample" data-m="На Starter не вижу экспорт CSV. Он вообще есть?" data-c="Текущий тариф: Starter.">CSV / Growth</button>
          <button class="sample" data-m="Хотим вход сотрудников через SAML SSO. Как подключить?" data-c="Компания масштабирует корпоративный доступ.">SSO / Enterprise</button>
          <button class="sample" data-m="Не приходит письмо для сброса пароля." data-c="">Без допродажи</button>
        </div>

        <button id="run" class="run">Сформировать подсказку</button>
      </div>

      <div class="card pane">
        <div class="output">
          <h2>Ответ клиенту</h2>
          <div id="client" class="text muted">Здесь появится сообщение, которое можно отправить клиенту.</div>
        </div>

        <div class="output manager">
          <h2>Подсказка менеджеру · не отправлять клиенту</h2>
          <div id="manager" class="text muted">Здесь появится рекомендация по следующему действию и релевантной допродаже.</div>
          <div id="meta" class="meta"></div>
        </div>

        <div class="output">
          <h2>Опора в базе знаний</h2>
          <div id="sources" class="muted">После анализа здесь будут показаны использованные документы.</div>
        </div>
      </div>
    </section>
  </main>

  <script>
    const message = document.getElementById("message");
    const context = document.getElementById("context");
    const run = document.getElementById("run");
    const client = document.getElementById("client");
    const manager = document.getElementById("manager");
    const meta = document.getElementById("meta");
    const sources = document.getElementById("sources");

    document.querySelectorAll(".sample").forEach(btn => {
      btn.addEventListener("click", () => {
        message.value = btn.dataset.m;
        context.value = btn.dataset.c;
      });
    });

    run.addEventListener("click", async () => {
      run.disabled = true;
      run.textContent = "Анализирую…";
      client.className = "text muted";
      manager.className = "text muted";
      client.textContent = "Готовлю grounded-ответ…";
      manager.textContent = "Проверяю, есть ли уместная допродажа…";
      meta.innerHTML = "";
      sources.innerHTML = "";

      try {
        const response = await fetch("/api/assist", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({
            client_message: message.value,
            manager_context: context.value
          })
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || "Request failed");

        client.className = "text";
        manager.className = "text";
        client.textContent = data.client_reply;
        manager.textContent = data.manager_hint;

        const confidence = document.createElement("span");
        confidence.className = "chip";
        confidence.textContent = "confidence " + data.confidence;
        meta.appendChild(confidence);

        if (data.upsell_product) {
          const upsell = document.createElement("span");
          upsell.className = "chip";
          upsell.textContent = "upsell: " + data.upsell_product;
          meta.appendChild(upsell);
        }

        if (!data.sources.length) {
          sources.textContent = "Надёжные источники не выбраны — сервис ушёл в безопасный fallback.";
          sources.className = "muted";
        } else {
          sources.className = "";
          data.sources.forEach(item => {
            const link = document.createElement("a");
            link.className = "source";
            link.href = item.url;
            link.target = "_blank";
            link.rel = "noreferrer";
            link.textContent = item.title + " · score " + item.score;
            sources.appendChild(link);
          });
        }
      } catch (err) {
        client.className = "text error";
        manager.className = "text error";
        client.textContent = "Ошибка запуска прототипа.";
        manager.textContent = String(err.message || err);
      } finally {
        run.disabled = false;
        run.textContent = "Сформировать подсказку";
      }
    });
  </script>
</body>
</html>
"""
