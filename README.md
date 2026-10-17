# Kilombino's Umbrel app store

Community app store for umbrelOS with apps for the Bitcoin BLAKE2b chain (XBT).

## Add it to your Umbrel

App Store → ⋯ (top right) → **Community App Stores** → paste:

```
https://github.com/Kilombino/umbrel-store
```

## Apps

| App | What it is |
| --- | --- |
| [ThunderHub XBT](kilombino-thunderhub-xbt) | ThunderHub forked for the BLAKE2b chain, managing a Lightning Fork node |
| [Kilowallet](kilombino-kilowallet) | The Kilowallet XBT wallet with a web app for the phone, on your BLAKE2b node: Knots (BLAKE2b) Companion or the Misc store's Bitcoin Knots, found by itself |

ThunderHub XBT needs **Lightning Fork** (LND for the BLAKE2b chain) from the PaulsCode.Com store, which in turn needs a Bitcoin node on the BLAKE2b chain. Kilowallet needs a node on the BLAKE2b chain: **Knots (BLAKE2b) Companion** from the same store, or **Bitcoin Knots** from Léo Haf's Misc store (`https://github.com/Horizon-btc/Bitcoin-store`), and finds it by itself. Add the PaulsCode.Com store:

```
https://github.com/paulscode/umbrel-store
```

Kilowallet checks the node's chain and refuses the SHA-256 chain (the Bitcoin Node app, and the Umbrel App Store's Bitcoin Knots 1.2.13). Needs umbrelOS 1.3 or later.
