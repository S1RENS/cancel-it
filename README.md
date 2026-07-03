# 🚫 Cancel-It

**The "Abilene Paradox" solver — find out if anyone actually wants to go, without asking.**

One person creates a poll, drops the link in the group chat, and everyone votes
**secretly**. Nothing is revealed until the last vote is in. If a majority would
rather cancel, the event is cancelled — no names, no blame, sweatpants for
everyone.

Built with Python and Streamlit.

## 📖 The Problem: The Abilene Paradox

In sociology, the Abilene Paradox occurs when a group of people collectively decide on a course of action that is counter to the preferences of many (or all) of the individuals in the group. It stems from a breakdown of communication where each member mistakenly believes that their own preferences are contrary to the group's, and therefore does not raise objections.

> Example: Four friends agree to drive to Abilene for dinner. It is a hot, dusty drive. They arrive, eat a mediocre meal, and return home exhausted. Once back, they realize that none of them actually wanted to go; they only agreed because they thought the others wanted to.

Cancel-It solves this by introducing private preference aggregation. It allows the group to discover the "True Will" of the collective without exposing the "Social Face" of the individual.

## 🕳 The Black Box Guarantees

- **No notifications** are sent when someone votes.
- While voting is open, only the **count** of votes cast is visible ("3 of 5 votes are in") — never who voted or how.
- When the last vote lands, everyone sees **only the verdict**: cancelled or confirmed. Individual votes are never revealed, and no tallies are shown.

## ⏳ Voting window

Every poll has a deadline, chosen at creation (1–48 hours, default 24). When
time runs out, the poll concludes with the votes that are in — nobody can hold
the group hostage by not voting. Silent participants count as going with the
group (they don't add to the cancel tally, but they still count toward the
majority threshold). Votes cast after the deadline are rejected.

## 💾 Data & retention

Polls live in a single SQLite file on the server (`data/cancelit.db` by
default) as JSON blobs — no accounts, no emails, no analytics
(`gatherUsageStats` is off). Retention:

- Poll rows are **deleted 30 days after creation** (pruning runs whenever a new
  poll is created). Until then, anyone with the link can view the poll page —
  which shows only the vote count while active and only the verdict afterwards.
- Raw votes are stored unencrypted in that file, so whoever operates the server
  could technically read them. On Streamlit Community Cloud that disk is also
  **ephemeral**: polls disappear entirely whenever the app is redeployed or the
  container is recycled.

## ⚖️ Weighting

| Option      | Icon | Weight (Towards Cancel) | Semantic Meaning                                                                                     |
| ----------- | ---- | ----------------------- | ---------------------------------------------------------------------------------------------------- |
| Go          | 🟢  | 0.0                     | "I want to go." This vote actively fights against cancellation.                                      |
| Soft Cancel | 🟡  | 1.0                     | "I prefer not to, but I'll follow the group." (Treats polite hesitation as a valid vote to opt-out). |
| Hard Cancel | 🔴  | 1.0                     | "I am not going." (Mathematically identical to Soft Cancel, but represents a definitive boundary).   |
| Wingman     | 🔗  | Variable                | "I go only if [Name] goes." (Resolves recursively before the count).                                 |

The event is cancelled when cancel votes exceed 50% of the group.

## 🔗 Wingman system

Your vote can be automatically adjusted based on who is attending.

1. The Pair: Alice needs Bob $\leftrightarrow$ Bob needs Alice.
    - Result: Both GO. (The Pact).
2. The Train: Alice needs Bob $\rightarrow$ Bob needs Charlie $\rightarrow$ Charlie needs Alice.
    - Result: All GO. (The Group Pact).
3. The Broken Chain: Alice needs Bob $\rightarrow$ Bob needs Charlie $\rightarrow$ Charlie Hard Cancels.
    - Result: All CANCEL. (The Domino Effect).

## 🚀 Run locally

```shell
uv sync
uv run streamlit run src/app.py
```

Polls are stored in a local SQLite database (`data/cancelit.db` by default), so
they survive restarts.

### Configuration

| Env var           | Default            | Purpose                                                                 |
| ----------------- | ------------------ | ----------------------------------------------------------------------- |
| `CANCELIT_DB_PATH`| `data/cancelit.db` | Where the SQLite database lives.                                        |
| `BASE_URL`        | *(auto-detected)*  | Overrides the domain used in share links (useful behind reverse proxies). Can also be set in `.streamlit/secrets.toml`. |

Share links normally auto-detect the URL the visitor is using, so `BASE_URL` is
rarely needed.

## ☁️ Deploy to Streamlit Community Cloud (free)

This gives you a public `https://<your-app>.streamlit.app` link you can drop
straight into WhatsApp.

1. Push this repo to GitHub (already done if you're reading this there).
2. Go to [share.streamlit.io](https://share.streamlit.io) and sign in with GitHub.
3. Click **Create app** → **Deploy a public app from GitHub**.
4. Pick this repository and branch.
5. Set **Main file path** to `src/app.py`.
6. Open **Advanced settings** and select **Python 3.13**.
7. Click **Deploy**. Dependencies install automatically from `uv.lock`.

That's it — the app builds the share links from its own public URL
automatically.

> **Storage caveat:** Community Cloud's disk is ephemeral. Polls survive app
> restarts and sleeping, but not a re-deploy or re-provisioning of the
> container. Since polls only need to live for a few hours, this is usually
> fine. Self-host with Docker if you need durable storage.

## 🐳 Deploy with Docker (self-hosted)

```shell
docker build -t cancel-it .
docker run -p 8501:8501 -v cancelit-data:/data cancel-it
```

Polls persist in the `cancelit-data` volume across restarts. If you serve the
app behind a reverse proxy, set `-e BASE_URL=https://your.domain` so share
links use your public address.

## 🛠 Development

```shell
uv sync                      # install everything, incl. dev tools
uv run pytest                # tests
uv run ruff check .          # lint
uv run ruff format .         # format
uv run pre-commit install    # optional: hooks on commit
```

## 🛡 Security Note

This tool uses URL-based IDs (`?poll=<id>`). While the IDs are unguessable, anyone with the link can vote. Do not share poll links publicly; they are intended for private messaging groups (Signal/WhatsApp) only.

## FAQs

**1. Why does "Soft" have the same weight as "Hard"?**

**Scenario A: Weight = 1.0** (current weighting)
$$Score = 0 (Alice) + 1 (Bob) + 1 (Charlie) = 2$$
$$Threshold = 1.5$$

Result: $2 > 1.5 \rightarrow$ CANCEL. (Success)

**Scenario B: Weight = 0.5**
$$Score = 0 (Alice) + 0.5 (Bob) + 0.5 (Charlie) = 1.0$$
$$Threshold = 1.5$$

Result: $1.0 < 1.5 \rightarrow$ GO. (Failure)

Conclusion: With 0.5 weighting, even if the majority (2 out of 3) vote "Soft Cancel," the event still happens. This is the Abilene Paradox, as most of the group would rather cancel.

**2. Can the outcome reveal how individuals voted?**

In tiny groups, sometimes — a cancelled 2-person poll mathematically outs both
voters no matter what the UI shows. The app never displays tallies or names,
which is the best any tool can do; the rest is arithmetic.

**3. What if someone votes under the wrong name?**

First vote wins: a name's vote is locked once cast and can't be overwritten
(this prevents tampering). If it really matters, create a fresh poll.
