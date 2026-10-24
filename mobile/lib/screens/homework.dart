import 'dart:async';

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

import '../api/models.dart';
import '../api/oe_api.dart';
import '../l10n/l10n.dart';
import '../state/counters.dart';
import '../state/session.dart';
import '../ui/icons.dart';
import '../ui/media.dart';
import '../ui/theme.dart';
import '../ui/widgets.dart';
import '../util/attach.dart';
import '../util/format.dart';
import 'home.dart';
import 'shell.dart';

enum HwFilter { active, review, checked }

HwFilter filterOf(Homework h) => switch (h.status) {
      'submitted' => HwFilter.review,
      'checked' => HwFilter.checked,
      _ => HwFilter.active,
    };

String hwIcon(Homework h) {
  final s = '${h.title} ${h.body ?? ''}'.toLowerCase();
  if (s.contains('голос') || s.contains('voice') || s.contains('speaking') || s.contains('аудио')) return 'mic';
  if (s.contains('essay') || s.contains('эссе') || s.contains('сочин')) return 'pencil';
  if (s.contains('test') || s.contains('тест') || s.contains('vocabulary')) return 'file';
  return 'book';
}

/// Screen 4a — homework by status; overdue is red (parents see it too).
class HomeworkListScreen extends StatefulWidget {
  const HomeworkListScreen({super.key});

  @override
  State<HomeworkListScreen> createState() => _HomeworkListScreenState();
}

class _HomeworkListScreenState extends State<HomeworkListScreen> {
  HwFilter _f = HwFilter.active;

  @override
  Widget build(BuildContext context) {
    final t = context.t;
    final s = context.watch<Session>();
    final c = s.child;
    return Column(children: [
      TabHeader(t.navHomework, actions: [if (!s.isParent) avatarAction(context)]),
      const ChildSwitcher(),
      if (c == null)
        const Expanded(child: NoChild())
      else
        Expanded(
          child: Loader<List<Homework>>(
            key: ValueKey('hw-${c.id}'),
            load: () => context.read<OeApi>().homework(c.id),
            builder: (context, items, reload) {
              final now = DateTime.now();
              final counts = {for (final f in HwFilter.values) f: items.where((h) => filterOf(h) == f).length};
              final shown = items.where((h) => filterOf(h) == _f).toList();
              if (_f == HwFilter.active) {
                shown.sort((a, b) => (a.dueAt ?? DateTime(2100)).compareTo(b.dueAt ?? DateTime(2100)));
              }
              return PageList(onRefresh: reload, children: [
                OeSegmented<HwFilter>(
                  value: _f,
                  onChanged: (v) => setState(() => _f = v),
                  options: [
                    (HwFilter.active, counts[HwFilter.active]! > 0 ? t.hwActiveN(counts[HwFilter.active]!) : t.hwActive),
                    (HwFilter.review, t.hwReview),
                    (HwFilter.checked, t.hwChecked),
                  ],
                ),
                if (shown.isEmpty)
                  EmptyState(icon: 'task', title: _f == HwFilter.active ? t.hwNoneActive : t.hwNone)
                else
                  OeList(children: [
                    for (final h in shown)
                      _HwRow(h: h, now: now, onTap: () async {
                        await context.push('/homework/${h.id}', extra: h);
                        reload();
                      }),
                  ]),
              ]);
            },
          ),
        ),
    ]);
  }
}

class _HwRow extends StatelessWidget {
  const _HwRow({required this.h, required this.now, required this.onTap});
  final Homework h;
  final DateTime now;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final oe = context.oe;
    final overdue = h.overdue(now);
    final tone = overdue ? (oe.red100, oe.red) : (h.status == 'checked' ? (oe.ok100, oe.ok) : (oe.navy100, oe.tint));
    return InkWell(
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          IconTile(hwIcon(h), bg: tone.$1, fg: tone.$2, size: 40, radius: 12),
          const SizedBox(width: 12),
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(h.title, style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 15)),
              if ((h.teacherComment ?? h.body) != null)
                Padding(
                  padding: const EdgeInsets.only(top: 2),
                  child: Text(h.status == 'checked' && h.teacherComment != null ? '«${h.teacherComment}»' : h.body!.split('\n').first,
                      maxLines: 1, overflow: TextOverflow.ellipsis, style: TextStyle(fontSize: 13, color: oe.muted)),
                ),
              const SizedBox(height: 8),
              hwPill(context, h, now),
            ]),
          ),
          OeIcon('chev-r', size: 20, color: oe.muted),
        ]),
      ),
    );
  }
}

/// Screen 4b — the task on top, the answer below; only the student account submits (text and one file).
class HomeworkDetailScreen extends StatefulWidget {
  const HomeworkDetailScreen({super.key, required this.id});
  final int id;

  @override
  State<HomeworkDetailScreen> createState() => _HomeworkDetailScreenState();
}

class _HomeworkDetailScreenState extends State<HomeworkDetailScreen> {
  final _answer = TextEditingController();
  Picked? _file;
  UploadedFile? _uploaded;
  bool _busy = false;
  bool _uploading = false;
  String? _error;
  VoiceRecorder? _rec;
  Timer? _recTick;
  bool _editing = false;

  @override
  void dispose() {
    _answer.dispose();
    _recTick?.cancel();
    _rec?.dispose();
    super.dispose();
  }

  Future<void> _attach(Future<Picked?> Function() pick) async {
    try {
      final p = await pick();
      if (p == null || !mounted) return;
      setState(() {
        _file = p;
        _uploaded = null;
        _uploading = true;
        _error = null;
      });
      final up = await context.read<OeApi>().upload(p.bytes, p.name, p.mime);
      if (mounted) setState(() => _uploaded = up);
    } catch (e) {
      if (mounted) {
        setState(() {
          _file = null;
          _error = errorText(context, e);
        });
      }
    } finally {
      if (mounted) setState(() => _uploading = false);
    }
  }

  Future<void> _toggleVoice() async {
    if (_rec != null) {
      final r = _rec!;
      _recTick?.cancel();
      setState(() => _rec = null);
      await _attach(() async {
        final p = await r.stop();
        await r.dispose();
        return p;
      });
      return;
    }
    final r = VoiceRecorder();
    try {
      if (!await r.start()) {
        if (mounted) toast(context, context.t.micDenied, error: true);
        await r.dispose();
        return;
      }
    } catch (e) {
      if (mounted) toast(context, context.t.micDenied, error: true);
      return;
    }
    setState(() => _rec = r);
    _recTick = Timer.periodic(const Duration(milliseconds: 500), (_) => setState(() {}));
  }

  Future<void> _submit(Homework h, int studentId) async {
    final t = context.t;
    final text = _answer.text.trim();
    if (text.isEmpty && _uploaded == null) {
      setState(() => _error = t.hwNoAnswer);
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await context.read<OeApi>().submitHomework(h.id, studentId, answer: text.isEmpty ? null : text, fileKey: _uploaded?.key);
      h.status = 'submitted';
      h.answer = text.isEmpty ? null : text;
      if (_uploaded != null) h.fileUrl = _uploaded!.url;
      if (!mounted) return;
      context.read<Counters>().refresh();
      toast(context, t.hwSent);
      setState(() {
        _editing = false;
        _file = null;
        _uploaded = null;
      });
    } catch (e) {
      if (mounted) setState(() => _error = errorText(context, e));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = context.t;
    final s = context.watch<Session>();
    final c = s.child;
    return Scaffold(
      appBar: NavBar(backLabel: t.navHomework, title: t.hwTask),
      body: c == null
          ? const NoChild()
          : Loader<Homework?>(
              key: ValueKey('hwd-${c.id}-${widget.id}'),
              load: () async => (await context.read<OeApi>().homework(c.id)).where((h) => h.id == widget.id).firstOrNull,
              builder: (context, h, reload) {
                if (h == null) return EmptyState(icon: 'task', title: t.hwNotFound);
                return _body(context, h, c.id, s.isStudent);
              },
            ),
    );
  }

  Widget _body(BuildContext context, Homework h, int studentId, bool student) {
    final t = context.t;
    final oe = context.oe;
    final now = DateTime.now();
    final canSubmit = student && h.status != 'checked';
    final compose = canSubmit && (h.status == 'assigned' || _editing);
    final rec = _rec;
    return Column(children: [
      Expanded(
        child: ListView(padding: const EdgeInsets.fromLTRB(16, 4, 16, 16), children: [
          Align(alignment: Alignment.centerLeft, child: hwPill(context, h, now)),
          const SizedBox(height: 8),
          Semantics(header: true, child: Text(h.title, style: display(21, color: oe.brandInk, height: 1.25))),
          if (h.dueAt != null)
            Padding(
              padding: const EdgeInsets.only(top: 4),
              child: Text(t.dueFull('${dmy(h.dueAt!)} ${hm(h.dueAt!)}'), style: TextStyle(fontSize: 13, color: oe.muted)),
            ),
          if (h.body != null) ...[
            const SizedBox(height: 12),
            OeCard(child: SelectableText(h.body!, style: const TextStyle(fontSize: 15, height: 1.45))),
          ],
          if (h.teacherComment != null || h.grade != null) ...[
            const SizedBox(height: 12),
            OeCard(
              color: oe.ok100,
              child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                if (h.grade != null) ...[
                  Container(
                    width: 40,
                    height: 40,
                    alignment: Alignment.center,
                    decoration: BoxDecoration(color: oe.ok, borderRadius: BorderRadius.circular(12)),
                    child: Text('${h.grade}', style: display(18, color: OeColors.white)),
                  ),
                  const SizedBox(width: 12),
                ],
                Expanded(
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Text(t.teacherComment, style: TextStyle(fontWeight: FontWeight.w600, color: oe.ok)),
                    if (h.teacherComment != null) Text(h.teacherComment!, style: TextStyle(color: oe.ink)),
                  ]),
                ),
              ]),
            ),
          ],
          const SizedBox(height: 16),
          SectionTitle(t.myAnswer),
          if (!compose) ...[
            if (h.answer == null && h.fileUrl == null)
              Text(student ? t.hwNotSubmitted : t.hwNoAnswerParent, style: TextStyle(color: oe.muted))
            else
              OeCard(
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  if (h.answer != null) SelectableText(h.answer!),
                  if (h.fileUrl != null) ...[
                    if (h.answer != null) const SizedBox(height: 10),
                    Attachment(url: h.fileUrl!, name: t.hwFile),
                  ],
                ]),
              ),
            if (canSubmit && h.status == 'submitted') ...[
              const SizedBox(height: 12),
              OeButton(t.hwRedo, kind: BtnKind.tonal, onPressed: () {
                _answer.text = h.answer ?? '';
                setState(() => _editing = true);
              }),
            ],
          ] else ...[
            TextField(
              key: const Key('hw-answer'),
              controller: _answer,
              minLines: 3,
              maxLines: 8,
              maxLength: 8000,
              decoration: InputDecoration(hintText: t.hwAnswerHint, counterText: ''),
            ),
            const SizedBox(height: 10),
            if (_file != null)
              Padding(
                padding: const EdgeInsets.only(bottom: 10),
                child: _uploading
                    ? Row(children: [
                        const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2)),
                        const SizedBox(width: 10),
                        Text(t.uploading, style: TextStyle(color: oe.muted)),
                      ])
                    : _file!.kind == 'voice' && _uploaded != null
                        ? Row(children: [
                            Expanded(child: OeCard(padding: const EdgeInsets.all(10), child: VoicePlayer(url: _uploaded!.url))),
                            IconButton(
                                tooltip: t.remove,
                                onPressed: () => setState(() => _file = _uploaded = null),
                                icon: OeIcon('x', color: oe.muted)),
                          ])
                        : FileTile(
                            name: _file!.name,
                            subtitle: '${(_file!.bytes.length / 1024).ceil()} KB',
                            onRemove: () => setState(() => _file = _uploaded = null)),
              ),
            if (rec != null)
              Padding(
                padding: const EdgeInsets.only(bottom: 10),
                child: Banner2(
                  tone: Tone.red,
                  icon: 'mic',
                  title: t.recording('${rec.elapsed.inMinutes}:${(rec.elapsed.inSeconds % 60).toString().padLeft(2, '0')}'),
                  text: t.recordingHint,
                  onTap: _toggleVoice,
                ),
              ),
            Row(children: [
              Expanded(child: _AddBox(icon: 'camera', label: t.photo, onTap: () => _attach(() => choosePhoto(context)))),
              const SizedBox(width: 8),
              Expanded(child: _AddBox(icon: 'mic', label: rec != null ? t.stop : t.voice, onTap: _toggleVoice, active: rec != null)),
              const SizedBox(width: 8),
              Expanded(child: _AddBox(icon: 'clip', label: t.file, onTap: () => _attach(pickDocument))),
            ]),
            const SizedBox(height: 6),
            Text(t.hwOneFile, style: TextStyle(fontSize: 12, color: oe.muted)),
          ],
          if (_error != null)
            Padding(padding: const EdgeInsets.only(top: 10), child: Text(_error!, style: TextStyle(color: oe.red))),
        ]),
      ),
      if (compose)
        SafeArea(
          top: false,
          child: Padding(
            padding: const EdgeInsets.fromLTRB(16, 4, 16, 12),
            child: OeButton(t.hwSubmit,
                key: const Key('hw-submit'),
                loading: _busy,
                onPressed: _uploading || rec != null ? null : () => _submit(h, studentId)),
          ),
        ),
    ]);
  }
}

class _AddBox extends StatelessWidget {
  const _AddBox({required this.icon, required this.label, required this.onTap, this.active = false});
  final String icon;
  final String label;
  final VoidCallback onTap;
  final bool active;

  @override
  Widget build(BuildContext context) {
    final oe = context.oe;
    return Semantics(
      button: true,
      label: label,
      excludeSemantics: true,
      child: InkWell(
        borderRadius: BorderRadius.circular(14),
        onTap: onTap,
        child: CustomPaint(
          painter: OeStyle.ios ? _Dashed(active ? oe.red : oe.outline) : null,
          child: Container(
            padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 4),
            decoration: OeStyle.ios
                ? null
                : BoxDecoration(borderRadius: BorderRadius.circular(12), border: Border.all(color: active ? oe.red : oe.outline)),
            child: Column(children: [
              OeIcon(icon, color: active ? oe.red : oe.tint),
              const SizedBox(height: 6),
              Text(label, style: TextStyle(fontSize: 13, fontWeight: FontWeight.w500, color: active ? oe.red : oe.tint)),
            ]),
          ),
        ),
      ),
    );
  }
}

class _Dashed extends CustomPainter {
  _Dashed(this.color);
  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    final p = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.5;
    final path = Path()..addRRect(RRect.fromRectAndRadius(Offset.zero & size, const Radius.circular(14)));
    for (final m in path.computeMetrics()) {
      for (double d = 0; d < m.length; d += 9) {
        canvas.drawPath(m.extractPath(d, d + 5), p);
      }
    }
  }

  @override
  bool shouldRepaint(_Dashed old) => old.color != color;
}
