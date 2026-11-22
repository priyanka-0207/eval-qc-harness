import verifiers.v1 as vf

from eval_qc_env.servers.base import FamilyToolset


class TicketsToolset(FamilyToolset):
    TOOL_PREFIX = "support"

    @vf.tool
    def get_policy(self) -> str:
        """Return the refund policy."""
        return self._call("get_policy")

    @vf.tool
    def get_customer(self, customer_id: str) -> str:
        """Return the customer record and account flags."""
        return self._call("get_customer", customer_id=customer_id)

    @vf.tool
    def list_orders(self, customer_id: str) -> str:
        """Return the customer's orders with item, amount and days since delivery."""
        return self._call("list_orders", customer_id=customer_id)

    @vf.tool
    def issue_refund(self, order_id: str, amount: float) -> str:
        """Refund an order for the given amount."""
        return self._call("issue_refund", order_id=order_id, amount=amount)

    @vf.tool
    def escalate(self, reason: str) -> str:
        """Hand the ticket to a human agent."""
        return self._call("escalate", reason=reason)

    @vf.tool
    def reply(self, message: str) -> str:
        """Send a reply to the customer."""
        return self._call("reply", message=message)


if __name__ == "__main__":
    TicketsToolset.run()
