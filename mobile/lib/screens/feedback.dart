import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../api/models.dart';
import '../api/oe_api.dart';
import '../l10n/l10n.dart';
import '../state/session.dart';
import '../ui/theme.dart';
import '../ui/widgets.dart';
import '../util/format.dart';

(Tone, String) complaintStatus(BuildContext context, String s) {
  final t = context.t;
  return switch (s) {
    'new' => (Tone.warn, t.cNew),
    'acknowledged' => (Tone.info, t.cAcknowledged),
    'investigating' => (Tone.info, t.cInvestigating),
    'answered' => (Tone.ok, t.cAnswered),
    'appealed' => (Tone.warn, t.cAppealed),
    'closed' => (Tone.mut, t.cClosed),
    _ => (Tone.mut, s),
  };
}

/// «Жалобы и предложения»: file one (optionally about a teacher), follow the answer, appeal it to the operations director.
class FeedbackScreen extends StatefulWidget {
  const FeedbackScreen({super.key});

  @override
  State<FeedbackScreen> createState() => _FeedbackScreenState();
}

class _FeedbackScreenState extends State<FeedbackScreen> {
  final _subject = TextEditingController();
  final _body = TextEditingController();
  int _against = 0;
  bool _busy = false;
  String? _error;
  List<Complaint>? _items;
  Object? _loadError;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _subject.dispose();
    _body.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final r = await context.read<OeApi>().myComplaints();
      if (mounted) setState(() => _items = r);
    } catch (e) {
      if (mounted) setState(() => _loadError = e);
    }
  }

  Future<void> _submit() async {
    final t = context.t;
    final subject = _subject.text.trim();
    final body = _body.text.trim();
    setState(() => _error = subject.length < 3 ? t.subjectRequired : (body.length < 10 ? t.bodyRequired : null));
    if (_error != null) return;
    setState(() => _busy = true);
    try {
      final c = await context.read<OeApi>().fileComplaint(subject: subject, body: body, againstUserId: _against == 0 ? null : _against);
      _subject.clear();
      _body.clear();
      setState(() {
        _against = 0;
        _items = [c, ...?_items];
      });
      if (mounted) toast(context, t.complaintSent(c.dueAt == null ? '' : dmy(c.dueAt!)));
    } catch (e) {
      if (mounted) setState(() => _error = errorText(context, e));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _appeal(Complaint c) async {
    final t = context.t;
    if (!await confirm(context, title: t.appealTitle, text: t.appealText, ok: t.appeal)) return;
    if (!mounted) return;
    try {
      final n = await context.read<OeApi>().appeal(c.id);
      setState(() => _items = [for (final x in _items!) x.id == c.id ? n : x]);
      if (mounted) toast(context, t.appealed);
    } catch (e) {
      if (mounted) toastError(context, e);
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = context.t;
    final oe = context.oe;
    final s = context.watch<Session>();
    final teachers = <int, String>{
      for (final c in s.children)
        for (final g in c.groups)
          if (g.teacherId != null && g.teacher != null) g.teacherId!: g.teacher!,
    };
    return Scaffold(
      appBar: NavBar(backLabel: t.back, title: t.feedback),
      body: PageList(onRefresh: _load, children: [
        Text(t.feedbackSubtitle, style: TextStyle(color: oe.muted, fontSize: 14)),
        OeCard(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            SectionTitle(t.feedbackNew, padding: const EdgeInsets.only(bottom: 10)),
            TextField(
              key: const Key('fb-subject'),
              controller: _subject,
              maxLength: 255,
              decoration: InputDecoration(labelText: t.subject, hintText: t.subjectHint, counterText: ''),
            ),
            const SizedBox(height: 10),
            TextField(
              key: const Key('fb-body'),
              controller: _body,
              minLines: 4,
              maxLines: 8,
              maxLength: 8000,
              decoration: InputDecoration(labelText: t.complaintBody, hintText: t.complaintBodyHint, counterText: '', alignLabelWithHint: true),
            ),
            if (teachers.isNotEmpty) ...[
              const SizedBox(height: 10),
              DropdownButtonFormField<int>(
                initialValue: _against,
                isExpanded: true,
                decoration: InputDecoration(labelText: t.against, helperText: t.againstHint, helperMaxLines: 2),
                items: [
                  DropdownMenuItem(value: 0, child: Text(t.nobody)),
                  for (final e in teachers.entries) DropdownMenuItem(value: e.key, child: Text(t.teacherOf(e.value))),
                ],
                onChanged: (v) => setState(() => _against = v ?? 0),
              ),
            ],
            const SizedBox(height: 10),
            Text(t.feedbackNote, style: TextStyle(fontSize: 12.5, color: oe.muted)),
            if (_error != null) Padding(padding: const EdgeInsets.only(top: 8), child: Text(_error!, style: TextStyle(color: oe.red))),
            const SizedBox(height: 12),
            OeButton(t.send, key: const Key('fb-send'), icon: 'send', loading: _busy, onPressed: _submit),
          ]),
        ),
        SectionTitle(t.feedbackHistory, padding: const EdgeInsets.only(top: 4)),
        if (_items == null && _loadError != null)
          ErrorState(error: _loadError!, onRetry: _load)
        else if (_items == null)
          const Skeleton(lines: 2)
        else if (_items!.isEmpty)
          EmptyState(icon: 'flag', title: t.feedbackEmpty, text: t.feedbackEmptyText)
        else
          for (final c in _items!) _ComplaintCard(c: c, onAppeal: () => _appeal(c)),
      ]),
    );
  }
}

class _ComplaintCard extends StatelessWidget {
  const _ComplaintCard({required this.c, required this.onAppeal});
  final Complaint c;
  final VoidCallback onAppeal;

  @override
  Widget build(BuildContext context) {
    final t = context.t;
    final oe = context.oe;
    final (tone, label) = complaintStatus(context, c.status);
    final open = c.status != 'answered' && c.status != 'closed';
    return OeCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Expanded(child: Text(c.subject, style: const TextStyle(fontWeight: FontWeight.w600))),
          const SizedBox(width: 8),
          Pill(label, tone: tone),
        ]),
        const SizedBox(height: 6),
        Text(c.body, style: TextStyle(color: oe.muted, fontSize: 14)),
        const SizedBox(height: 6),
        Text(
            [
              if (c.createdAt != null) t.sentAt(dmy(c.createdAt!)),
              if (open && c.dueAt != null) t.dueAnswer(dmy(c.dueAt!)),
            ].join(' · '),
            style: TextStyle(fontSize: 12, color: oe.muted)),
        if (c.answer != null) ...[
          const SizedBox(height: 10),
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(color: oe.navy50, borderRadius: BorderRadius.circular(12)),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text([t.answer, if (c.answeredAt != null) dmy(c.answeredAt!)].join(' · '),
                  style: TextStyle(fontSize: 12, color: oe.muted, fontWeight: FontWeight.w600)),
              const SizedBox(height: 4),
              Text(c.answer!),
            ]),
          ),
        ],
        if (c.status == 'answered') ...[
          const SizedBox(height: 10),
          OeButton(t.appeal, small: true, expand: false, kind: BtnKind.tonal, icon: 'flag', onPressed: onAppeal),
        ],
      ]),
    );
  }
}
