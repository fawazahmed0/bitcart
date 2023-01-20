from api import crud, invoices, models, settings, utils
from api.events import event_handler
from api.ext.configurator import deploy_task
from api.ext.shopify import shopify_invoice_update
from api.logger import get_exception_message, get_logger
from api.plugins import run_hook

logger = get_logger(__name__)


@event_handler.on("expired_task")
async def create_expired_task(event, event_data):
    invoice = await utils.database.get_object(models.Invoice, event_data["id"], raise_exception=False)
    if not invoice:
        return
    await invoices.make_expired_task(invoice)


@event_handler.on("send_verification_email")
async def send_verification_email(event, event_data):
    user = await utils.database.get_object(models.User, event_data["id"], raise_exception=False)
    if not user:
        return
    await crud.users.send_verification_email(user, event_data["next_url"])


@event_handler.on("sync_wallet")
async def sync_wallet(event, event_data):
    model = await utils.database.get_object(models.Wallet, event_data["id"], raise_exception=False)
    if not model:
        return
    coin = await settings.settings.get_coin(
        model.currency, {"xpub": model.xpub, "contract": model.contract, **model.additional_xpub_data}
    )
    try:
        balance = await coin.balance()
    except Exception as e:
        logger.error(f"Wallet {model.id} failed to sync:\n{get_exception_message(e)}")
        await utils.redis.publish_message(f"wallet:{model.id}", {"status": "error", "balance": 0})
        return
    await run_hook("wallet_synced", model, balance)
    logger.info(f"Wallet {model.id} synced, balance: {balance['confirmed']}")
    await utils.redis.publish_message(
        f"wallet:{model.id}", {"status": "success", "balance": str(balance["confirmed"])}
    )  # convert for json serialization


event_handler.add_handler("deploy_task", deploy_task)
event_handler.add_handler("invoice_status", shopify_invoice_update)
