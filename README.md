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
| [Kilowallet (Bitcoin Knots)](kilombino-kilowallet-knots) | The same wallet, on the Bitcoin Knots app from the Umbrel App Store running a Knots version with BLAKE2b |
| [Kilowallet (Bitcoin Knots, Misc store)](kilombino-kilowallet-misc) | The same wallet, on the Bitcoin Knots app of the Misc community store (Horizon-btc/Bitcoin-store), whose latest Knots versions have BLAKE2b |

ThunderHub XBT needs **Lightning Fork** (LND for the BLAKE2b chain) from the PaulsCode.Com store, which in turn needs a Bitcoin node on the BLAKE2b chain. Kilowallet needs that node, **Knots (BLAKE2b) Companion**, from the same store. Add that store too:

```
https://github.com/paulscode/umbrel-store
```

**Kilowallet (Bitcoin Knots)** is for the official **Bitcoin Knots** app instead (Umbrel App Store), with no other store and nothing to set up, as long as that app runs a Knots version that follows the BLAKE2b chain. Its version 1.2.13, the current one in the Umbrel App Store, offers none yet (the update with BLAKE2b, 1.2.18, is waiting to be accepted); on a node that is not on the BLAKE2b chain Kilowallet shows a page that says so and does nothing. Both Kilowallet apps check the node's chain and refuse the SHA-256 chain.
