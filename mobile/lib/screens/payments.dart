import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import '../api/models.dart';
import '../api/oe_api.dart';
import '../l10n/l10n.dart';
import '../state/session.dart';
import '../state/settings.dart';
import '../ui/icons.dart';
import '../ui/theme.dart';
import '../ui/widgets.dart';
import '../util/format.dart';
import 'shell.dart';

String methodLabel(BuildContext context, String m) {
  final t = context.t;
  return switch (m) {
    'cash' => t.payCash,
    'card' => t.payCard,
    'kaspi' => 'Kaspi',
    'transfer' => t.payTransfer,
    _ => m,
  };
}

/// Screen 10a — what the family owes first, then lessons and money per child, then the history.
/// Open while access is blocked: this is how a parent sees what to pay.
class PaymentsScreen extends StatelessWidget {
  const PaymentsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final t = context.t;
    final s = context.watch<Session>();
    final kids = s.children;
    return Column(children: [
      TabHeader(t.navPayments, actions: [
        HeaderAction('book', label: t.myBooks, onTap: () => context.push('/books')),
        if (!s.isParent) avatarAction(context),
      ]),
      if (kids.isEmpty)
        const Expanded(child: NoChild())
      else
        Expanded(
          child: Loader<List<(Child, Payments)>>(
            key: ValueKey('pay-${kids.map((k) => k.id).join(',')}'),
            load: () async {
              final api = context.read<OeApi>();
              final r = await Future.wait(kids.map((k) => api.payments(k.id)));
              return [for (var i = 0; i < kids.length; i++) (kids[i], r[i])];
            },
            builder: (context, data, reload) => _Body(data: data, reload: reload),
          ),
        ),
    ]);
  }
}

class _Body extends StatelessWidget {
  const _Body({required this.data, required this.reload});
  final List<(Child, Payments)> data;
  final Future<void> Function() reload;

  @override
  Widget build(BuildContext context) {
    final t = context.t;
    final oe = context.oe;
    final locale = context.watch<Settings>().locale;
    final s = context.read<Session>();
    final debtors = data.where((d) => d.$2.debtLessons > 0 || d.$2.blocked).toList();
    final total = debtors.fold<int>(0, (a, d) => a + (d.$2.debtAmount ?? 0));
    final history = [
      for (final d in data)
        for (final p in d.$2.items) (d.$1, p),
    ]..sort((a, b) => b.$2.paidAt.compareTo(a.$2.paidAt));
    return PageList(onRefresh: () async {
      await s.reloadPortal();
      await reload();
    }, children: [
      if (debtors.isNotEmpty)
        Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: oe.surface,
            borderRadius: BorderRadius.circular(OeStyle.cardRadius),
            border: Border.all(color: oe.red100, width: 1.5),
          ),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Pill(debtors.any((d) => d.$2.blocked) ? t.blockedShort : t.debt, tone: Tone.red),
            const SizedBox(height: 10),
            Text(total > 0 ? money(total) : t.debtLessonsN(debtors.fold(0, (a, d) => a + d.$2.debtLessons)),
                style: display(34, color: oe.ink, height: 1.05)),
            const SizedBox(height: 6),
            for (final d in debtors)
              Text(
                  [
                    d.$1.firstName,
                    if (d.$1.mainGroup != null) d.$1.mainGroup!.name,
                    t.debtLessonsN(d.$2.debtLessons),
                    if (d.$2.lessonPrice != null) t.pricePer(money(d.$2.lessonPrice!)),
                  ].join(' · '),
                  style: TextStyle(fontSize: 13, color: oe.muted)),
            const SizedBox(height: 14),
            OeButton(t.howToPay, kind: BtnKind.red, onPressed: () => _howToPay(context, debtors.first.$1)),
            const SizedBox(height: 8),
            Center(child: Text(t.onlineSoon, style: TextStyle(fontSize: 12, color: oe.muted))),
          ]),
        ),
      OeList(children: [
        for (final d in data)
          OeRow(
            leading: Avatar(d.$1.fullName, size: 36),
            title: d.$1.firstName,
            titleStyle: const TextStyle(fontWeight: FontWeight.w600),
            subtitle: [
              if (d.$1.mainGroup != null) d.$1.mainGroup!.name,
              if (d.$2.lessonPrice != null) t.pricePer(money(d.$2.lessonPrice!)),
            ].join(' · '),
            trailing: Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
              Text(t.lessonsN(d.$2.lessonsLeft),
                  style: TextStyle(fontWeight: FontWeight.w600, color: d.$2.lessonsLeft <= 0 ? oe.red : oe.ink)),
              Text(d.$2.lessonsLeft <= 0 ? t.needPayment : t.onBalance(money(d.$2.moneyBalance)),
                  style: TextStyle(fontSize: 12, color: oe.muted)),
            ]),
          ),
      ]),
      SectionTitle(t.history, padding: const EdgeInsets.only(top: 4)),
      if (history.isEmpty)
        EmptyState(icon: 'wallet', title: t.noPayments)
      else
        OeList(children: [
          for (final h in history)
            OeRow(
              leading: h.$2.category == 'book'
                  ? IconTile('book', size: 36)
                  : IconTile('check', size: 36, bg: oe.ok100, fg: oe.ok),
              title: h.$2.category == 'book'
                  ? (h.$2.note ?? t.bookPurchase)
                  : [if (data.length > 1) h.$1.firstName, if (h.$2.lessons > 0) t.lessonsN(h.$2.lessons) else t.payCategory(h.$2.category)]
                      .join(' · '),
              titleStyle: const TextStyle(fontWeight: FontWeight.w600, fontSize: 13.5),
              subtitle: [dayMonth(h.$2.paidAt, locale), methodLabel(context, h.$2.method), if (h.$2.category != 'book' && h.$2.note != null) h.$2.note!]
                  .join(' · '),
              trailing: Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
                Text(money(h.$2.amount), style: const TextStyle(fontWeight: FontWeight.w600)),
                if (h.$2.refunded > 0) Text(t.refunded(money(h.$2.refunded)), style: TextStyle(fontSize: 12, color: oe.red)),
              ]),
            ),
        ]),
    ]);
  }
}

/// 10b — online payment isn't connected yet: call the branch or write to the manager.
Future<void> _howToPay(BuildContext context, Child c) async {
  final t = context.t;
  final r = await pickAction<String>(context,
      title: t.payFor(c.firstName),
      message: t.payHowText,
      options: [
        if (c.branch.phone != null) ('call', t.callBranch(c.branch.name), 'phone'),
        ('chat', t.writeManager, 'chat'),
      ]);
  if (!context.mounted) return;
  if (r == 'call') {
    launchUrl(Uri.parse('tel:${c.branch.phone!.replaceAll(' ', '')}'));
  } else if (r == 'chat') {
    context.push('/chats/new');
  }
}

/// Books bought at the school (from the payment history, category «book»).
class BooksScreen extends StatelessWidget {
  const BooksScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final t = context.t;
    final s = context.watch<Session>();
    final c = s.child;
    final locale = context.watch<Settings>().locale;
    return Scaffold(
      appBar: NavBar(backLabel: t.back, title: t.myBooks, subtitle: s.isParent ? c?.firstName : null),
      body: c == null
          ? const NoChild()
          : Column(children: [
              const ChildSwitcher(),
              Expanded(
                child: Loader<Payments>(
                  key: ValueKey('books-${c.id}'),
                  load: () => context.read<OeApi>().payments(c.id),
                  builder: (context, p, reload) => PageList(onRefresh: reload, children: [
                    if (c.level != null) OeCard(child: Text(t.booksLevel(c.level!), style: TextStyle(color: context.oe.muted))),
                    if (p.books.isEmpty)
                      EmptyState(icon: 'book', title: t.noBooks, text: t.noBooksText)
                    else
                      OeList(children: [
                        for (final b in p.books)
                          OeRow(
                            leading: IconTile('book', size: 36),
                            title: b.note ?? t.bookPurchase,
                            subtitle: '${dayMonth(b.paidAt, locale)} · ${methodLabel(context, b.method)}',
                            trailing: Text(money(b.amount), style: const TextStyle(fontWeight: FontWeight.w600)),
                          ),
                      ]),
                  ]),
                ),
              ),
            ]),
    );
  }
}

/// The receipt icon used in headers.
Widget receiptIcon(BuildContext context) => OeIcon('receipt', color: context.oe.tint);
