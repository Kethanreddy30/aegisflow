from cache.keys import make_cache_key
from gateway.schemas import ChatMessage


def test_cache_key_is_tenant_isolated():
    messages = [
        ChatMessage(
            role="user",
            content="Hello world",
        )
    ]

    key_a = make_cache_key(
        tenant_id="tenant-a",
        model="gpt-4",
        messages=messages,
    )

    key_b = make_cache_key(
        tenant_id="tenant-b",
        model="gpt-4",
        messages=messages,
    )

    assert key_a != key_b


def test_cache_key_is_deterministic():
    messages = [
        ChatMessage(
            role="user",
            content="Hello world",
        )
    ]

    key_1 = make_cache_key(
        tenant_id="tenant-a",
        model="gpt-4",
        messages=messages,
    )

    key_2 = make_cache_key(
        tenant_id="tenant-a",
        model="gpt-4",
        messages=messages,
    )

    assert key_1 == key_2
