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
| [Kilowallet](kilombino-kilowallet) | The Kilowallet XBT wallet with a web app for the phone, on Knots (BLAKE2b) Companion |
| [Kilowallet (Bitcoin Knots)](kilombino-kilowallet-misc) | The same wallet, on Léo Haf's Bitcoin Knots app from the Misc community store (Horizon-btc/Bitcoin-store), whose latest Knots versions have BLAKE2b |

ThunderHub XBT needs **Lightning Fork** (LND for the BLAKE2b chain) from the PaulsCode.Com store, which in turn needs a Bitcoin node on the BLAKE2b chain. Kilowallet needs that node, **Knots (BLAKE2b) Companion**, from the same store. Add that store too:

```
https://github.com/paulscode/umbrel-store
```

**Kilowallet (Bitcoin Knots)** is for Léo Haf's **Bitcoin Knots** app from the Misc community store instead, whose latest Knots versions follow the BLAKE2b chain; nothing to set up. Add that store: `https://github.com/Horizon-btc/Bitcoin-store`. (The Bitcoin Knots app of the Umbrel App Store, version 1.2.13, has no Knots version with BLAKE2b yet.) Both Kilowallet apps check the node's chain and refuse the SHA-256 chain.
