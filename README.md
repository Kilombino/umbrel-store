# Kilombino's Umbrel app store

Community app store for umbrelOS with apps for the Bitcoin BLAKE2b chain (BTC).

## Add it to your Umbrel

App Store → ⋯ (top right) → **Community App Stores** → paste:

```
https://github.com/Kilombino/umbrel-store
```

## Apps

| App | What it is |
| --- | --- |
| [ThunderHub XBT](kilombino-thunderhub-xbt) | ThunderHub forked for the BLAKE2b chain, managing a Lightning Fork node |
| [JoinMarket XBT (Jam)](kilombino-jam-xbt) | JoinMarket-NG for the BLAKE2b chain with the Jam web wallet: CoinJoin as a taker or a maker, on your BLAKE2b node, found by itself |
| [Roblosats](kilombino-roblosats) | The Roblosats client (RoboSats for the BLAKE2b chain): P2P exchange over Lightning with every coordinator of the Roblosats federation, over Umbrel's Tor. Needs umbrelOS 2.0 (HTTPS) |
| [Roblosats Coordinator](kilombino-roblosats-coordinator) | Run your own Roblosats coordinator (beta): the Roblosats server, its database, Nostr relay and onion, on Lightning Fork and Knots (BLAKE2b) Companion |
| [Kilowallet](kilombino-kilowallet) | The Kilowallet Bitcoin (BLAKE2b) wallet with a web app for the phone, on your BLAKE2b node: Knots (BLAKE2b) Companion or the Misc store's Bitcoin Knots, found by itself |
| [Mempool Kilombino](kilombino-mempool) | The explorer of mempool.kilombino.com for the BLAKE2b chain, with the Bitcoin Nodes World Map, on Knots (BLAKE2b) Companion (unpruned, txindex on) and Electrs Pruned |
| [Lightning Stream](kilombino-lightning-stream) | Lazarus's Lightning Stream, unchanged (same images and digests): buy and sell services over Lightning, and rent hashrate peer to peer. Install it from one store only |
| [Lightning XBT](kilombino-lightning-xbt) | Paul Lamb's Lightning Fork (LND for the BLAKE2b chain), with the dashboard changes Kilombino proposed to Paul that are not released yet (newest payments first, Mempool Kilombino and any Mempool app). Installs beside Lightning Fork, on ports of its own |
| [Bitcoin Knots](kilombino-bitcoin-knots) | Bitcoin Knots 29.4.3, a full node on the BLAKE2b chain: Horizon BTC and Léo Haf's Bitcoin Knots app, same images, on ports of its own (P2P 18454, RPC 18453) so it installs beside any other node app |
| [DATUM CONVOY](kilombino-datum-convoy) | CONVOY's DATUM Gateway v0.5.0beta with CONVOY #7, #4, #38 and #40 (Kilombino's own build), on the Bitcoin node you choose; stratum on 23338 |
| [MRR Command Center](kilombino-mrr-command-center) | Rent BLAKE2b hashrate on MiningRigRentals by hand and check what each rental delivers to your DATUM CONVOY. Asks for your MRR API key after you sign in |

ThunderHub XBT needs **Lightning Fork** (LND for the BLAKE2b chain) from the PaulsCode.Com store, which in turn needs a Bitcoin node on the BLAKE2b chain. Kilowallet and JoinMarket XBT (Jam) need a node on the BLAKE2b chain: **Knots (BLAKE2b) Companion** from the same store, or **Bitcoin Knots** from Léo Haf's Misc store (`https://github.com/Horizon-btc/Bitcoin-store`), and finds it by itself. Add the PaulsCode.Com store:

```
https://github.com/paulscode/umbrel-store
```

Kilowallet checks the node's chain and refuses the SHA-256 chain (the Bitcoin Node app, and the Umbrel App Store's Bitcoin Knots 1.2.13). Needs umbrelOS 1.3 or later.
