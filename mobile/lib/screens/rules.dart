import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../api/models.dart';
import '../api/oe_api.dart';
import '../l10n/l10n.dart';
import '../state/session.dart';
import '../ui/icons.dart';
import '../ui/theme.dart';
import '../ui/widgets.dart';
import '../util/format.dart';

/// Plain-text document body as the school publishes it: `#` or short unpunctuated lines are headings,
/// `-`/`•` lines are list items, runs of `a | b | c` lines are a table (shown as cards on a phone).
class DocBody extends StatelessWidget {
  const DocBody(this.body, {super.key});
  final String body;

  static final _bullet = RegExp(r'^\s*[-•*☐]\s+');
  static final _hash = RegExp(r'^#{1,6}\s');

  static bool _heading(String l) {
    if (_hash.hasMatch(l)) return true;
    final t = l.trim();
    if (t.length > 70 || t.contains(' | ') || _bullet.hasMatch(l)) return false;
    if (RegExp(r'[.:;!?,»)]$').hasMatch(t)) return false;
    return RegExp(r'^[A-ZА-ЯЁӘҒҚҢӨҰҮҺІ]').hasMatch(t);
  }

  @override
  Widget build(BuildContext context) {
    final oe = context.oe;
    final lines = body.replaceAll('\r', '').split('\n').map((l) => l.trimRight()).where((l) => l.trim().isNotEmpty).toList();
    final out = <Widget>[];
    for (var i = 0; i < lines.length; i++) {
      final l = lines[i];
      if (l.contains(' | ')) {
        final rows = <List<String>>[];
        while (i < lines.length && lines[i].contains(' | ')) {
          rows.add(lines[i].split('|').map((c) => c.trim()).toList());
          i++;
        }
        i--;
        final head = rows.first;
        out.add(Column(children: [
          for (final r in rows.skip(1))
            Container(
              width: double.infinity,
              margin: const EdgeInsets.only(bottom: 8),
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(color: oe.fill, borderRadius: BorderRadius.circular(12)),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(r.first, style: const TextStyle(fontWeight: FontWeight.w600)),
                for (var c = 1; c < r.length; c++)
                  Padding(
                    padding: const EdgeInsets.only(top: 3),
                    child: Text.rich(TextSpan(children: [
                      if (c < head.length) TextSpan(text: '${head[c]}: ', style: TextStyle(color: oe.muted)),
                      TextSpan(text: r[c]),
                    ]), style: const TextStyle(fontSize: 13.5, height: 1.35)),
                  ),
              ]),
            ),
        ]));
      } else if (_bullet.hasMatch(l)) {
        out.add(Padding(
          padding: const EdgeInsets.only(bottom: 5),
          child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(l.trim().startsWith('☐') ? '☐  ' : '•  ', style: TextStyle(color: oe.tint)),
            Expanded(child: Text(l.replaceFirst(_bullet, ''), style: const TextStyle(height: 1.45))),
          ]),
        ));
      } else if (_heading(l)) {
        out.add(Padding(
          padding: EdgeInsets.only(top: out.isEmpty ? 0 : 8, bottom: 6),
          child: Semantics(header: true, child: Text(l.replaceFirst(RegExp(r'^#+\s*'), ''), style: display(15, color: oe.brandInk))),
        ));
      } else {
        out.add(Padding(padding: const EdgeInsets.only(bottom: 8), child: Text(l, style: const TextStyle(height: 1.45))));
      }
    }
    return SelectionArea(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: out));
  }
}

/// Blocks the app until the current platform rules are accepted (when /auth/me lags behind the published version).
class RulesGateScreen extends StatefulWidget {
  const RulesGateScreen({super.key});

  @override
  State<RulesGateScreen> createState() => _RulesGateScreenState();
}

class _RulesGateScreenState extends State<RulesGateScreen> {
  bool _agree = false;
  bool _busy = false;

  Future<void> _accept() async {
    setState(() => _busy = true);
    try {
      await context.read<Session>().acceptRules();
    } catch (e) {
      if (mounted) toastError(context, e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = context.t;
    final oe = context.oe;
    final s = context.watch<Session>();
    final doc = s.rules;
    if (doc == null) return const SizedBox();
    return Scaffold(
      body: SafeArea(
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 16, 20, 8),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              IconTile('shield', size: 48, radius: 16),
              const SizedBox(height: 12),
              Semantics(
                  header: true,
                  child: Text(s.me?.rulesAcceptedVersion != null ? t.rulesUpdated : t.rulesGateTitle,
                      style: display(22, color: oe.brandInk))),
              const SizedBox(height: 6),
              Text(t.rulesGateText(doc.version, doc.effectiveFrom == null ? '' : dmy(doc.effectiveFrom!)),
                  style: TextStyle(color: oe.muted)),
            ]),
          ),
          Expanded(
            child: Container(
              margin: const EdgeInsets.symmetric(horizontal: 16),
              decoration: BoxDecoration(
                  color: oe.surface, borderRadius: BorderRadius.circular(OeStyle.cardRadius), border: Border.all(color: oe.line)),
              child: ListView(padding: const EdgeInsets.all(16), children: [
                Text(doc.title, style: display(17, color: oe.brandInk)),
                const SizedBox(height: 10),
                DocBody(doc.body),
              ]),
            ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 12),
            child: Column(children: [
              CheckboxListTile.adaptive(
                key: const Key('agree'),
                value: _agree,
                onChanged: (v) => setState(() => _agree = v ?? false),
                contentPadding: EdgeInsets.zero,
                controlAffinity: ListTileControlAffinity.leading,
                title: Text(t.rulesAgree, style: const TextStyle(fontSize: 14)),
              ),
              OeButton(t.rulesAccept, key: const Key('accept-rules'), loading: _busy, onPressed: _agree ? _accept : null),
              TextButton(onPressed: () => s.signOut(), child: Text(t.logout, style: TextStyle(color: oe.muted))),
            ]),
          ),
        ]),
      ),
    );
  }
}

/// Rules and the lesson-recording consent. Parents sign the recording consent for each child.
class RulesScreen extends StatefulWidget {
  const RulesScreen({super.key, this.tab});
  final String? tab;

  @override
  State<RulesScreen> createState() => _RulesScreenState();
}

class _RulesScreenState extends State<RulesScreen> {
  late String _kind = widget.tab == 'recording' ? 'recording' : 'rules';
  String? _busy;

  @override
  Widget build(BuildContext context) {
    final t = context.t;
    return Scaffold(
      appBar: NavBar(backLabel: t.back, title: t.rulesTitle),
      body: Loader<(DocVersion?, DocVersion?, List<MyConsent>)>(
        load: () async {
          final api = context.read<OeApi>();
          final r = await Future.wait<Object?>([api.document('rules'), api.document('recording'), api.myConsents()]);
          return (r[0] as DocVersion?, r[1] as DocVersion?, r[2] as List<MyConsent>);
        },
        builder: (context, d, reload) => _body(context, d, reload),
      ),
    );
  }

  Widget _body(BuildContext context, (DocVersion?, DocVersion?, List<MyConsent>) d, Future<void> Function() reload) {
    final t = context.t;
    final oe = context.oe;
    final s = context.watch<Session>();
    final doc = _kind == 'rules' ? d.$1 : d.$2;
    MyConsent? consentFor(int? studentId) =>
        d.$3.where((c) => c.documentId == doc?.id && c.studentId == studentId && c.revokedAt == null).firstOrNull;

    Future<void> accept(int? studentId) async {
      setState(() => _busy = 'a$studentId');
      try {
        if (doc!.kind == 'rules') {
          await s.acceptRules();
        } else {
          await context.read<OeApi>().acceptDocument(doc.id, studentId: studentId);
        }
        if (context.mounted) toast(context, t.consentSaved);
        await reload();
      } catch (e) {
        if (context.mounted) toastError(context, e);
      } finally {
        if (mounted) setState(() => _busy = null);
      }
    }

    Future<void> revoke(MyConsent c) async {
      if (!await confirm(context, title: t.revokeTitle, text: t.revokeText, ok: t.revoke, danger: true)) return;
      if (!context.mounted) return;
      try {
        await context.read<OeApi>().revokeConsent(c.id);
        if (context.mounted) toast(context, t.revoked);
        await reload();
      } catch (e) {
        if (context.mounted) toastError(context, e);
      }
    }

    Widget signRow(String title, int? studentId) {
      final c = consentFor(studentId);
      return OeRow(
        title: title,
        titleStyle: const TextStyle(fontWeight: FontWeight.w600),
        subtitle: c?.acceptedAt == null ? t.notSigned : t.signedAt(dmy(c!.acceptedAt!)),
        trailing: c != null
            ? OeButton(t.revoke, small: true, expand: false, kind: BtnKind.ghost, onPressed: () => revoke(c))
            : OeButton(t.sign,
                key: Key('sign-${studentId ?? 'me'}'),
                small: true,
                expand: false,
                loading: _busy == 'a$studentId',
                onPressed: _busy == null ? () => accept(studentId) : null),
      );
    }

    return PageList(onRefresh: reload, children: [
      OeSegmented<String>(
        value: _kind,
        onChanged: (v) => setState(() => _kind = v),
        options: [('rules', t.tabRules), ('recording', t.tabRecording)],
      ),
      if (doc == null)
        EmptyState(icon: 'file', title: t.docNotPublished)
      else ...[
        if (_kind == 'rules')
          s.me?.rulesAcceptedVersion == doc.version
              ? Banner2(tone: Tone.ok, icon: 'check', title: t.rulesAcceptedV(doc.version))
              : OeButton(t.rulesAccept, loading: _busy != null, onPressed: () => accept(null))
        else ...[
          Text(s.isParent ? t.recordingParent : t.recordingSelf, style: TextStyle(color: oe.muted, fontSize: 14)),
          OeList(children: [
            if (s.isParent)
              for (final c in s.children) signRow(c.fullName, c.id)
            else
              signRow(s.me?.fullName ?? '', null),
          ]),
        ],
        OeCard(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(doc.title, style: display(17, color: oe.brandInk)),
            const SizedBox(height: 4),
            Text(t.docVersion(doc.version, doc.effectiveFrom == null ? '' : dmy(doc.effectiveFrom!)),
                style: TextStyle(fontSize: 13, color: oe.muted)),
            if (doc.upcomingVersion != null) ...[
              const SizedBox(height: 10),
              Banner2(title: t.docUpcoming(doc.upcomingVersion!, doc.upcomingFrom == null ? '' : dmy(doc.upcomingFrom!))),
            ],
            const SizedBox(height: 12),
            DocBody(doc.body),
          ]),
        ),
      ],
    ]);
  }
}

/// Small icon for the rules link in lists.
Widget rulesIcon(BuildContext context) => OeIcon('file', color: context.oe.tint);
