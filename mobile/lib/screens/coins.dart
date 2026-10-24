import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

import '../api/models.dart';
import '../api/oe_api.dart';
import '../l10n/l10n.dart';
import '../state/session.dart';
import '../state/settings.dart';
import '../ui/icons.dart';
import '../ui/media.dart';
import '../ui/theme.dart';
import '../ui/widgets.dart';
import '../util/format.dart';
import 'shell.dart';

enum CoinTab { shop, rating, history }

class CoinsData {
  CoinsData(this.history, this.items, this.orders);
  final CoinHistory history;
  final List<ShopItem> items;
  final List<ShopOrder> orders;
}

/// Screens 6a/6b — balance, the shop (order → ready → issued), the leaderboard and the history.
class CoinsScreen extends StatefulWidget {
  const CoinsScreen({super.key, this.initial = CoinTab.shop});
  final CoinTab initial;

  @override
  State<CoinsScreen> createState() => _CoinsScreenState();
}

class _CoinsScreenState extends State<CoinsScreen> {
  late CoinTab _tab = widget.initial;

  @override
  Widget build(BuildContext context) {
    final t = context.t;
    final s = context.watch<Session>();
    final c = s.child;
    return Column(children: [
      TabHeader(t.navCoins, actions: [
        HeaderAction('receipt', label: t.orders, onTap: () => context.push('/orders')),
        if (!s.isParent) avatarAction(context),
      ]),
      const ChildSwitcher(),
      if (c == null)
        const Expanded(child: NoChild())
      else
        Expanded(
          child: Loader<CoinsData>(
            key: ValueKey('coins-${c.id}'),
            load: () async {
              final api = context.read<OeApi>();
              final r = await Future.wait<Object>([api.coins(c.id), api.shopItems(c.branch.id), api.orders(c.id)]);
              return CoinsData(r[0] as CoinHistory, r[1] as List<ShopItem>, r[2] as List<ShopOrder>);
            },
            builder: (context, d, reload) => _Body(child: c, data: d, tab: _tab, onTab: (v) => setState(() => _tab = v), reload: reload),
          ),
        ),
    ]);
  }
}

class _Body extends StatefulWidget {
  const _Body({required this.child, required this.data, required this.tab, required this.onTab, required this.reload});
  final Child child;
  final CoinsData data;
  final CoinTab tab;
  final ValueChanged<CoinTab> onTab;
  final Future<void> Function() reload;

  @override
  State<_Body> createState() => _BodyState();
}

class _BodyState extends State<_Body> {
  late int _balance = widget.data.history.balance;
  int? _busy;

  @override
  void didUpdateWidget(covariant _Body old) {
    super.didUpdateWidget(old);
    if (old.data != widget.data) _balance = widget.data.history.balance;
  }

  Future<void> _buy(ShopItem i) async {
    final t = context.t;
    final s = context.read<Session>();
    if (!await confirm(context, title: t.buyTitle, text: t.buyText(i.name, num(i.priceCoins)), ok: t.exchange)) return;
    if (!mounted) return;
    setState(() => _busy = i.id);
    try {
      final bal = await context.read<OeApi>().order(widget.child.id, i.id);
      setState(() {
        _balance = bal;
        i.stock -= 1;
      });
      widget.child.coins = bal;
      if (mounted) toast(context, t.ordered(i.name));
      s.reloadPortal();
      widget.reload();
    } catch (e) {
      if (mounted) toastError(context, e);
    } finally {
      if (mounted) setState(() => _busy = null);
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = context.t;
    final oe = context.oe;
    final d = widget.data;
    final week = d.history.earnedSince(DateTime.now().subtract(const Duration(days: 7)));
    final recent = d.history.items.where((e) => e.delta > 0 && e.reason != null && !e.kind.startsWith('order_')).take(4).toList();
    final open = d.orders.where((o) => o.open).length;
    return PageList(onRefresh: widget.reload, children: [
      OeCard(
        child: Row(children: [
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(t.myBalance, style: TextStyle(fontSize: 13, color: oe.muted)),
              const SizedBox(height: 6),
              Row(children: [
                const Coin(size: 40),
                const SizedBox(width: 10),
                Flexible(
                    child: FittedBox(
                        fit: BoxFit.scaleDown,
                        child: Text(num(_balance), key: const Key('coin-balance'), style: display(40, color: oe.ink, height: 1)))),
              ]),
            ]),
          ),
          if (week > 0) Pill(t.perWeek(week), tone: Tone.ok),
        ]),
      ),
      if (recent.isNotEmpty)
        SizedBox(
          height: 32,
          child: ListView(scrollDirection: Axis.horizontal, children: [
            for (final e in recent)
              Padding(padding: const EdgeInsets.only(right: 6), child: OeChip('${e.reason} +${e.delta}')),
          ]),
        ),
      if (open > 0)
        Banner2(
          icon: 'bag',
          title: t.openOrders(open),
          text: d.orders.any((o) => o.status == 'ready') ? t.orderReadyHint : t.orderPlacedHint,
          onTap: () => context.push('/orders'),
        ),
      OeSegmented<CoinTab>(
        value: widget.tab,
        onChanged: widget.onTab,
        options: [(CoinTab.shop, t.shop), (CoinTab.rating, t.rating), (CoinTab.history, t.history)],
      ),
      ...switch (widget.tab) {
        CoinTab.shop => [_shop(context, d.items)],
        CoinTab.rating => [_Leaderboard(child: widget.child)],
        CoinTab.history => [CoinHistoryList(history: d.history)],
      },
    ]);
  }

  Widget _shop(BuildContext context, List<ShopItem> items) {
    final t = context.t;
    final oe = context.oe;
    if (items.isEmpty) return EmptyState(icon: 'bag', title: t.shopEmpty);
    final blocked = widget.child.blocked;
    return LayoutBuilder(builder: (context, box) {
      final w = (box.maxWidth - 10) / 2;
      return Wrap(spacing: 10, runSpacing: 10, children: [
        for (final i in items)
          SizedBox(
            width: w,
            child: Container(
              clipBehavior: Clip.antiAlias,
              decoration: BoxDecoration(
                color: oe.surface,
                borderRadius: BorderRadius.circular(OeStyle.cardRadius),
                border: OeStyle.ios ? Border.all(color: oe.line) : null,
                boxShadow: OeStyle.ios ? null : const [BoxShadow(color: Color(0x0F0F1A33), blurRadius: 2, offset: Offset(0, 1))],
              ),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Container(
                  height: 96,
                  width: double.infinity,
                  color: oe.chip,
                  alignment: Alignment.center,
                  child: i.photoUrl != null
                      ? NetImage(url: i.photoUrl!, width: w, height: 96)
                      : OeIcon(shopIcon(i.icon), size: 56, color: oe.tint, duo: .2),
                ),
                Padding(
                  padding: const EdgeInsets.fromLTRB(12, 10, 12, 12),
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Text(i.name, maxLines: 2, overflow: TextOverflow.ellipsis, style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 14, height: 1.25)),
                    const SizedBox(height: 6),
                    Row(children: [
                      const Coin(size: 18),
                      const SizedBox(width: 6),
                      Text(num(i.priceCoins), style: display(15, color: oe.ink)),
                    ]),
                    const SizedBox(height: 8),
                    if (i.stock <= 0)
                      Text(t.outOfStock, style: TextStyle(fontSize: 12.5, color: oe.red))
                    else if (_balance < i.priceCoins)
                      Text(t.needMore(num(i.priceCoins - _balance)), style: TextStyle(fontSize: 12.5, color: oe.muted))
                    else
                      OeButton(t.exchange,
                          key: Key('buy-${i.id}'),
                          small: true,
                          kind: BtnKind.tonal,
                          loading: _busy == i.id,
                          onPressed: blocked || _busy != null ? null : () => _buy(i)),
                  ]),
                ),
              ]),
            ),
          ),
      ]);
    });
  }
}

class _Leaderboard extends StatefulWidget {
  const _Leaderboard({required this.child});
  final Child child;

  @override
  State<_Leaderboard> createState() => _LeaderboardState();
}

class _LeaderboardState extends State<_Leaderboard> {
  late bool _group = widget.child.mainGroup != null;

  @override
  Widget build(BuildContext context) {
    final t = context.t;
    final oe = context.oe;
    final c = widget.child;
    final g = c.mainGroup;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Wrap(spacing: 8, children: [
        if (g != null) OeChip(t.groupN(g.name), selected: _group, onTap: () => setState(() => _group = true)),
        OeChip(t.branchShort, selected: !_group, onTap: () => setState(() => _group = false)),
      ]),
      const SizedBox(height: 14),
      Loader<List<LeaderRow>>(
        key: ValueKey('top-${c.id}-$_group'),
        skeletonLines: 3,
        load: () => context.read<OeApi>().leaderboard(groupId: _group ? g?.id : null, branchId: _group ? null : c.branch.id),
        builder: (context, rows, _) {
          if (rows.isEmpty) return EmptyState(icon: 'trophy', title: t.noRating);
          final mine = rows.where((r) => r.name == c.firstName).length == 1 ? c.firstName : null;
          final podium = rows.take(3).toList();
          Widget step(int i, double h) {
            if (i >= podium.length) return const Expanded(child: SizedBox());
            final r = podium[i];
            final me = r.name == mine;
            return Expanded(
              flex: i == 0 ? 11 : 10,
              child: Column(mainAxisAlignment: MainAxisAlignment.end, children: [
                Avatar(r.name, size: i == 0 ? 56 : 44),
                const SizedBox(height: 6),
                Text(me ? t.you : r.name, style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 13)),
                Text(num(r.coins), style: TextStyle(fontSize: 13, color: oe.muted)),
                const SizedBox(height: 6),
                Container(
                  height: h,
                  margin: const EdgeInsets.symmetric(horizontal: 4),
                  alignment: Alignment.center,
                  decoration: BoxDecoration(
                    color: me ? oe.primary : oe.navy100,
                    borderRadius: const BorderRadius.vertical(top: Radius.circular(12), bottom: Radius.circular(4)),
                  ),
                  child: Text('${i + 1}', style: display(18, color: me ? oe.onPrimary : oe.tint)),
                ),
              ]),
            );
          }

          return Column(children: [
            SizedBox(
              height: 210,
              child: Row(crossAxisAlignment: CrossAxisAlignment.end, children: [step(1, 56), step(0, 80), step(2, 44)]),
            ),
            if (rows.length > 3) ...[
              const SizedBox(height: 12),
              OeList(children: [
                for (var i = 3; i < rows.length; i++)
                  Container(
                    color: rows[i].name == mine ? oe.navy50 : null,
                    padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 9),
                    child: Row(children: [
                      SizedBox(width: 24, child: Text('${i + 1}', style: TextStyle(fontWeight: FontWeight.w600, color: oe.muted))),
                      Avatar(rows[i].name, size: 36),
                      const SizedBox(width: 12),
                      Expanded(child: Text(rows[i].name == mine ? t.you : rows[i].name)),
                      Text(num(rows[i].coins), style: const TextStyle(fontWeight: FontWeight.w600)),
                    ]),
                  ),
              ]),
            ],
          ]);
        },
      ),
    ]);
  }
}

class CoinHistoryList extends StatelessWidget {
  const CoinHistoryList({super.key, required this.history});
  final CoinHistory history;

  @override
  Widget build(BuildContext context) {
    final t = context.t;
    final oe = context.oe;
    final locale = context.watch<Settings>().locale;
    if (history.items.isEmpty) return EmptyState(icon: 'coin', title: t.noCoinHistory);
    String label(CoinEntry e) => switch (e.kind) {
          'order_hold' => t.coinOrder(e.reason ?? ''),
          'order_release' => t.coinOrderCancelled,
          _ => e.reason ?? t.coinAward,
        };
    return OeList(children: [
      for (final e in history.items)
        OeRow(
          leading: IconTile(e.delta >= 0 ? 'coin' : 'bag', size: 36, bg: e.delta >= 0 ? oe.coin100 : oe.fill, fg: e.delta >= 0 ? oe.coin : oe.muted),
          title: label(e),
          subtitle: '${dayMonth(e.at, locale)}, ${hm(e.at)}',
          trailing: Text('${e.delta > 0 ? '+' : ''}${num(e.delta)}',
              style: TextStyle(fontWeight: FontWeight.w700, color: e.delta >= 0 ? oe.ok : oe.ink)),
        ),
    ]);
  }
}

/// Coin history as its own page (deep link).
class CoinHistoryScreen extends StatelessWidget {
  const CoinHistoryScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final c = context.watch<Session>().child;
    return Scaffold(
      appBar: NavBar(backLabel: context.t.navCoins, title: context.t.history),
      body: c == null
          ? const NoChild()
          : Loader<CoinHistory>(
              load: () => context.read<OeApi>().coins(c.id),
              builder: (context, h, reload) => PageList(onRefresh: reload, children: [CoinHistoryList(history: h)]),
            ),
    );
  }
}

/// Shop orders: placed → ready (pick up at the branch) → issued; a new order can be cancelled (coins return).
class OrdersScreen extends StatelessWidget {
  const OrdersScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final t = context.t;
    final s = context.watch<Session>();
    final c = s.child;
    final locale = context.watch<Settings>().locale;
    return Scaffold(
      appBar: NavBar(backLabel: t.navCoins, title: t.orders, subtitle: s.isParent ? c?.firstName : null),
      body: c == null
          ? const NoChild()
          : Loader<List<ShopOrder>>(
              key: ValueKey('orders-${c.id}'),
              load: () => context.read<OeApi>().orders(c.id),
              builder: (context, orders, reload) {
                if (orders.isEmpty) return EmptyState(icon: 'bag', title: t.noOrders);
                return PageList(onRefresh: reload, children: [
                  OeList(children: [
                    for (final o in orders)
                      OeRow(
                        key: Key('order-${o.id}'),
                        leading: IconTile('bag', size: 36),
                        title: o.item,
                        titleStyle: const TextStyle(fontWeight: FontWeight.w600),
                        subtitle: [
                          if (o.createdAt != null) dayMonth(o.createdAt!, locale),
                          t.coinsN(o.coins),
                          if (o.status == 'ready') t.pickUp,
                        ].join(' · '),
                        trailing: Row(mainAxisSize: MainAxisSize.min, children: [
                          Pill(_status(context, o.status), tone: switch (o.status) {
                            'placed' => Tone.warn,
                            'ready' => Tone.info,
                            'issued' => Tone.ok,
                            _ => Tone.mut,
                          }),
                          if (o.status == 'placed')
                            IconButton(
                              key: Key('cancel-${o.id}'),
                              tooltip: t.cancelOrder,
                              icon: OeIcon('x', size: 20, color: context.oe.muted),
                              onPressed: () async {
                                if (!await confirm(context,
                                    title: t.cancelOrderTitle, text: t.cancelOrderText(o.item, o.coins), ok: t.cancelOrder, danger: true)) {
                                  return;
                                }
                                if (!context.mounted) return;
                                try {
                                  await context.read<OeApi>().cancelOrder(o.id);
                                  if (context.mounted) {
                                    toast(context, t.orderCancelled);
                                    context.read<Session>().reloadPortal();
                                  }
                                  await reload();
                                } catch (e) {
                                  if (context.mounted) toastError(context, e);
                                }
                              },
                            ),
                        ]),
                      ),
                  ]),
                ]);
              },
            ),
    );
  }

  String _status(BuildContext context, String s) {
    final t = context.t;
    return switch (s) {
      'placed' => t.orderPlaced,
      'ready' => t.orderReady,
      'issued' => t.orderIssued,
      'cancelled' => t.orderCancelledShort,
      _ => s,
    };
  }
}
