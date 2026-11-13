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
| [Bitcoin Knots](kilombino-bitcoin-knots) | Bitcoin Knots 29.5, a full node on the BLAKE2b chain: Horizon BTC and Léo Haf's Bitcoin Knots app, same images, on ports of its own (P2P 18454, RPC 18453) so it installs beside any other node app. Answers the `bitcoin` dependency of every app here |
| [Lightning XBT](kilombino-lightning-xbt) | Paul Lamb's Lightning Fork (LND for the BLAKE2b chain), with the dashboard changes Kilombino proposed to Paul that are not released yet (newest payments first, Mempool Kilombino and any Mempool app). Installs beside Lightning Fork, on ports of its own, and stands in for it in apps that ask for Lightning Fork |
| [Electrs Pruned (Kilombino)](kilombino-electrs-pruned) | Paul Lamb's Electrs Pruned (MIT), same images and digests, with all the credit to Paul: an Electrum server that indexes a pruned node. On port 50601, so it installs beside Paul's (50201), and stands in for it in apps that ask for Electrs Pruned |
| [ThunderHub XBT](kilombino-thunderhub-xbt) | ThunderHub forked for the BLAKE2b chain, managing Lightning XBT or Paul's Lightning Fork |
| [JoinBlaket](kilombino-jam-xbt) | JoinBlaket: JoinMarket-NG for the BLAKE2b chain with the Jam web wallet: CoinJoin as a taker or a maker, on your BLAKE2b node, found by itself |
| [Roblosats](kilombino-roblosats) | The Roblosats client (RoboSats for the BLAKE2b chain): P2P exchange over Lightning with every coordinator of the Roblosats federation, over Umbrel's Tor. Needs umbrelOS 2.0 (HTTPS) |
| [Roblosats Coordinator](kilombino-roblosats-coordinator) | Run your own Roblosats coordinator (beta): the Roblosats server, its database, Nostr relay and onion, on Lightning XBT or Lightning Fork and a BLAKE2b node |
| [Kilowallet](kilombino-kilowallet) | The Kilowallet Bitcoin (BLAKE2b) wallet with a web app for the phone, on your BLAKE2b node, found by itself |
| [Mempool Kilombino](kilombino-mempool) | The explorer of mempool.kilombino.com for the BLAKE2b chain, with the Bitcoin Nodes World Map, on a BLAKE2b node (unpruned, txindex on) and Electrs Pruned |
| [Lightning Stream](kilombino-lightning-stream) | Lazarus's Lightning Stream, unchanged (same images and digests): buy and sell services over Lightning, and rent hashrate peer to peer. Runs on Lightning XBT or Lightning Fork. Install it from one store only |
| [DATUM CONVOY](kilombino-datum-convoy) | CONVOY's DATUM Gateway v0.5.0beta with CONVOY #7, #4, #38 and #40 (Kilombino's own build), on the Bitcoin node you choose; stratum on 23338 |
| [MRR Command Center](kilombino-mrr-command-center) | Rent BLAKE2b hashrate on MiningRigRentals by hand and check what each rental delivers to your DATUM CONVOY. Asks for your MRR API key after you sign in |

## Everything from this store

Every dependency can be met with apps from this store alone. Install the
providers first, because umbrelOS only offers a community app as a
dependency once it is installed:

1. **Bitcoin Knots**: the `bitcoin` dependency (it declares `implements: [bitcoin]`).
2. **Lightning XBT**, for ThunderHub XBT, Roblosats Coordinator and Lightning
   Stream. They ask for Paul's Lightning Fork (`paulscode-lightning-fork`);
   Lightning XBT declares `implements: [paulscode-lightning-fork]` and fills
   Lightning Fork's variables, so either one works.
3. **Electrs Pruned (Kilombino)**, for Mempool Kilombino, the same way for
   `paulscode-electrs-pruned`.

When an app asks, pick the provider in Umbrel's dialog. Apps from the
PaulsCode.Com store (`https://github.com/paulscode/umbrel-store`), such as
Knots (BLAKE2b) Companion, Lightning Fork and Electrs Pruned, and Léo Haf's Misc
store (`https://github.com/Horizon-btc/Bitcoin-store`) work as well.

Kilowallet checks the node's chain and refuses the SHA-256 chain (the Bitcoin Node app, and the Umbrel App Store's Bitcoin Knots 1.2.13). Needs umbrelOS 1.3 or later.

## Credits

Lightning XBT and Electrs Pruned (Kilombino) are Paul Lamb's Lightning Fork and
Electrs Pruned (`https://github.com/paulscode/umbrel-store`, MIT; the license is
in each app's folder where Paul's files are copied). Bitcoin Knots is Horizon BTC
and Léo Haf's app. Lightning Stream is Lazarus's, unchanged.
