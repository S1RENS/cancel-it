import os

import streamlit as st

import config
import storage

st.set_page_config(
    page_title=config.APP_TITLE,
    page_icon=config.APP_ICON,
    initial_sidebar_state="collapsed",
)

# Hide Streamlit elements for "App-like" feel
st.markdown(
    """
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    </style>
    """,
    unsafe_allow_html=True,
)

VOTE_CHOICES = {
    "🟢 I'm going": {"type": "go"},
    "🟡 I'd rather not, but I'll follow the group": {"type": "soft"},
    "🔴 I'm not going": {"type": "hard"},
    "🔗 I go only if someone else goes": None,  # needs a wingman target
}


def get_base_url() -> str:
    """Base URL for share links: explicit override, else the URL the
    visitor is actually using, else the local dev default."""
    base = os.environ.get("BASE_URL")
    if not base:
        try:
            base = st.secrets.get("BASE_URL")
        except Exception:
            base = None
    if not base:
        base = st.context.url  # scheme+host+port+path, query params stripped
    if not base:
        base = "http://localhost:8501"
    return base.rstrip("/")


def parse_participants(raw: str) -> list[str]:
    """Split comma-separated names, validating count and uniqueness."""
    names = [n.strip() for n in raw.split(",") if n.strip()]
    if len(names) < 2:
        raise ValueError("You need at least 2 people for a group decision.")
    if len(names) > config.MAX_PARTICIPANTS:
        raise ValueError(
            f"That's a lot of friends! Max {config.MAX_PARTICIPANTS} people."
        )
    seen: dict[str, str] = {}
    for name in names:
        key = name.casefold()
        if key in seen:
            raise ValueError(
                f'"{name}" appears more than once. '
                "Give everyone a unique name (add a last initial?)."
            )
        seen[key] = name
    return names


def render_create_view() -> None:
    st.title(f"{config.APP_ICON} {config.APP_TITLE}")
    st.write("**Find out if anyone actually wants to go — without asking.**")
    with st.expander("How it works"):
        st.markdown(
            "1. List everyone invited and share the link in your group chat.\n"
            "2. Everyone votes **secretly**. Nobody sees anything until the "
            "last vote is in.\n"
            "3. If a majority would rather cancel, the event is cancelled — "
            "no names, no blame."
        )

    with st.form("create_form"):
        event_name = st.text_input(
            "What's the event? (optional)", placeholder="Friday dinner"
        )
        raw_names = st.text_area(
            "Who's invited?",
            placeholder="Alice, Bob, Charlie",
            help="First names, separated by commas.",
        )
        submitted = st.form_submit_button("Create secret vote", type="primary")

    if submitted:
        try:
            participants = parse_participants(raw_names)
        except ValueError as exc:
            st.error(str(exc))
        else:
            st.session_state["created_poll"] = storage.create_poll(
                participants, name=event_name.strip()
            )

    # Rendered outside the submit branch so it survives Streamlit reruns.
    poll_id = st.session_state.get("created_poll")
    if poll_id:
        st.success("Poll created!")
        st.code(f"{get_base_url()}/?poll={poll_id}", language=None)
        st.caption(
            "Paste this into your group chat. "
            "Votes are secret until everyone has voted."
        )
        if st.button("Create another poll"):
            st.session_state.pop("created_poll", None)
            st.rerun()


def render_outcome(poll: dict) -> None:
    if poll.get("name"):
        st.subheader(poll["name"])
    if poll["status"] == "cancelled":
        st.error("🛑 EVENT CANCELLED")
        st.write("The group has spoken. Sweatpants for everyone — no questions asked.")
    else:
        st.success("✅ EVENT IS ON")
        st.write("The group actually wants to go. See you there!")
        st.balloons()
    st.caption("Individual votes are never revealed. That's the whole point.")


def render_poll_view(poll_id: str) -> None:
    poll = storage.get_poll(poll_id)
    if poll is None:
        st.title(f"{config.APP_ICON} {config.APP_TITLE}")
        st.error("This poll doesn't exist or has expired.")
        st.link_button("Start your own", get_base_url())
        return

    if poll["status"] != "active":
        render_outcome(poll)
        return

    st.title("🤫 Secret Vote")
    if poll.get("name"):
        st.subheader(poll["name"])
    st.write("Vote secretly. Nothing is revealed until the last vote is in.")

    voted, total = len(poll["votes"]), len(poll["participants"])
    st.progress(voted / total, text=f"{voted} of {total} votes are in")

    # All participants are always listed so the dropdown never leaks
    # who has already voted.
    me = st.selectbox(
        "Who are you?",
        poll["participants"],
        index=None,
        placeholder="Select your name",
        key=f"voter::{poll_id}",
    )
    if me is None:
        return

    already_voted = me in poll["votes"] or st.session_state.get(f"voted::{poll_id}")
    if already_voted:
        st.info("Your vote is sealed. Waiting for the others…")
        if st.button("🔄 Refresh"):
            st.rerun()
        return

    choice = st.radio(
        f"{me}, what do you actually want?",
        list(VOTE_CHOICES),
        key=f"choice::{poll_id}",
    )
    vote = VOTE_CHOICES[choice]
    if vote is None:  # conditional: pick a wingman
        others = [p for p in poll["participants"] if p != me]
        wingman = st.selectbox(
            "Who's your wingman?",
            others,
            index=None,
            placeholder="Select a person",
            key=f"wingman::{poll_id}",
            help="Your vote copies theirs: they go, you go. They bail, you bail.",
        )
        vote = {"type": "conditional", "target": wingman} if wingman else None

    if st.button("🤫 Cast my secret vote", type="primary", disabled=vote is None):
        try:
            storage.cast_vote(poll_id, me, vote)
        except storage.PollConcludedError:
            pass  # someone finished it meanwhile; rerun shows the outcome
        st.session_state[f"voted::{poll_id}"] = True
        st.rerun()


def main() -> None:
    poll_id = st.query_params.get("poll")
    if poll_id:
        render_poll_view(poll_id)
    else:
        render_create_view()


main()
