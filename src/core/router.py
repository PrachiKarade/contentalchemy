from src.core.state import ContentState


def route_by_intent(state: ContentState) -> str:
    intent = state.get("intent")

    routes = {
        "research": "research",
        "blog": "blog",
        "linkedin": "linkedin",
        "image": "image",
        "strategy": "strategy",
        "multi": "multi",
    }

    if intent not in routes:
        raise ValueError(f"Unsupported intent: {intent!r}")

    return routes[intent]