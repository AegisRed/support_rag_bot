from __future__ import annotations

from itertools import cycle

from support_rag_bot.models import KBDocument


def build_seed_documents(source_sites: list[str]) -> list[KBDocument]:
    sites = source_sites or [
        "https://help.northstar.test",
        "https://billing.northstar.test",
        "https://status.northstar.test",
    ]
    site_iter = cycle(sites)

    def next_site() -> str:
        return next(site_iter)

    def make_url(path: str) -> tuple[str, str]:
        site = next_site()
        return site, f"{site}{path}"

    site, url = make_url("/kb/auth/reset-password")
    doc1 = KBDocument(
        doc_id="kb_auth_reset_password",
        title="Сброс пароля и повторная отправка письма",
        section="Авторизация",
        url=url,
        site=site,
        tags=["auth", "password", "email"],
        content=(
            "Если пользователь не получил письмо для сброса пароля, сначала нужно проверить папку spam и убедиться, "
            "что адрес введён без опечатки. Повторная отправка письма доступна не чаще одного раза в 60 секунд. "
            "Ссылка из письма действует 30 минут. Если срок истёк, пользователь должен запросить новую ссылку. "
            "Если письмо не приходит после двух попыток, оператор проверяет блокировку домена или корпоративный mail gateway."
        ),
    )

    site, url = make_url("/kb/security/2fa-recovery")
    doc2 = KBDocument(
        doc_id="kb_auth_2fa_recovery",
        title="Восстановление доступа при потере 2FA",
        section="Безопасность",
        url=url,
        site=site,
        tags=["2fa", "auth", "security"],
        content=(
            "Если пользователь потерял доступ к приложению 2FA, он может использовать резервные recovery codes. "
            "Если кодов нет, бот не должен обещать мгновенное отключение 2FA. Нужна проверка личности оператором: "
            "последние четыре цифры инвойса, дата последней оплаты и подтверждение домена рабочей почты. "
            "После проверки оператор вручную сбрасывает 2FA в течение одного рабочего дня."
        ),
    )

    site, url = make_url("/kb/billing/invoices")
    doc3 = KBDocument(
        doc_id="kb_billing_invoice_download",
        title="Где скачать инвойс и чек",
        section="Биллинг",
        url=url,
        site=site,
        tags=["billing", "invoice", "receipt"],
        content=(
            "Инвойсы и чеки доступны в разделе Workspace Settings → Billing → Documents. "
            "Документы генерируются автоматически после успешного списания. Если платёж помечен как pending, инвойс не создаётся. "
            "Пользователь с ролью Viewer не видит биллинг-раздел и должен запросить доступ у Owner или Admin."
        ),
    )

    site, url = make_url("/kb/billing/cancel-subscription")
    doc4 = KBDocument(
        doc_id="kb_billing_cancel_subscription",
        title="Отмена подписки и что происходит после отмены",
        section="Биллинг",
        url=url,
        site=site,
        tags=["billing", "subscription", "cancel"],
        content=(
            "Подписку может отменить только Owner workspace. После отмены доступ не отключается сразу: он действует до конца уже оплаченного периода. "
            "Возврат средств за частично использованный период не производится, кроме случаев двойного списания или технической ошибки биллинга. "
            "Если клиент просит отмену из-за некорректного чарджа, бот должен не обещать refund автоматически, а отправить кейс оператору."
        ),
    )

    site, url = make_url("/kb/data/export-csv")
    doc5 = KBDocument(
        doc_id="kb_workspace_export_csv",
        title="Экспорт данных в CSV и его ограничения",
        section="Данные",
        url=url,
        site=site,
        tags=["export", "csv", "data"],
        content=(
            "Экспорт в CSV доступен на тарифах Growth и Enterprise. На тарифе Starter кнопка Export скрыта. "
            "Один экспорт может содержать до 50 000 строк. Для больших выгрузок система автоматически разбивает данные на несколько файлов. "
            "Если экспорт завис в статусе Processing дольше 15 минут, можно безопасно перезапустить задачу из журнала exports."
        ),
    )

    site, url = make_url("/kb/api/rate-limits")
    doc6 = KBDocument(
        doc_id="kb_api_rate_limits",
        title="API rate limits и ошибка 429",
        section="API",
        url=url,
        site=site,
        tags=["api", "rate-limit", "429"],
        content=(
            "Базовый лимит API составляет 120 запросов в минуту на workspace и 20 запросов в минуту на один API token. "
            "При превышении лимита сервер возвращает HTTP 429 с заголовком Retry-After. Рекомендуем exponential backoff: 2, 4, 8 секунд. "
            "Если клиенту нужен повышенный лимит, бот не должен обещать upgrade вручную: нужно отправить запрос оператору с workspace id и ожидаемой нагрузкой."
        ),
    )

    site, url = make_url("/kb/integrations/webhooks-retries")
    doc7 = KBDocument(
        doc_id="kb_webhooks_retry_policy",
        title="Повторные доставки webhook",
        section="Интеграции",
        url=url,
        site=site,
        tags=["webhooks", "retry", "integrations"],
        content=(
            "Если webhook endpoint отвечает кодом не из диапазона 2xx, система считает доставку неуспешной. "
            "Повторы выполняются по схеме 1 минута, 5 минут, 15 минут, 1 час, 6 часов. Всего до 5 повторов. "
            "События старше 24 часов больше не переотправляются. Для диагностики пользователь должен сверить delivery id и server logs на своей стороне."
        ),
    )

    site, url = make_url("/kb/enterprise/sso-requirements")
    doc8 = KBDocument(
        doc_id="kb_sso_requirements",
        title="Требования для настройки SSO",
        section="Enterprise",
        url=url,
        site=site,
        tags=["sso", "saml", "enterprise"],
        content=(
            "SSO через SAML доступен только на тарифе Enterprise. Для настройки нужны SSO URL, Entity ID, X.509 certificate и домен, который будет принудительно матчиться. "
            "Если у клиента тариф не Enterprise, бот не должен описывать настройку как уже доступную функцию. Корректный ответ: сначала нужен апгрейд тарифа, затем подключение через команду support."
        ),
    )

    site, url = make_url("/status")
    doc9 = KBDocument(
        doc_id="kb_status_incidents",
        title="Где смотреть инциденты и статус сервисов",
        section="Статус платформы",
        url=url,
        site=site,
        tags=["status", "incident", "uptime"],
        content=(
            "Текущий статус платформы публикуется на status-странице. Запланированные работы и активные инциденты отображаются отдельно. "
            "Если пользователь сообщает о массовой недоступности, бот может направить его на status-страницу, но не должен объявлять инцидент подтверждённым без записи на этой странице. "
            "При локальной ошибке у одного клиента нужна дополнительная диагностика, а не ссылка на общий статус."
        ),
    )

    return [doc1, doc2, doc3, doc4, doc5, doc6, doc7, doc8, doc9]
