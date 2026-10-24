
import 'package:file_picker/file_picker.dart';
import 'package:flutter/foundation.dart';
import 'package:image_picker/image_picker.dart';
import 'package:path_provider/path_provider.dart';
import 'package:record/record.dart';

/// A picked or recorded file ready for POST /api/files.
class Picked {
  Picked(this.bytes, this.name, this.mime, {this.kind = 'file'});
  final Uint8List bytes;
  final String name;
  final String mime;

  /// Chat message kind: image, file or voice.
  final String kind;

  bool get isImage => mime.startsWith('image/');
}

/// Content types the server accepts (services/files.py), by extension.
const _mimes = {
  'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'png': 'image/png', 'webp': 'image/webp', 'gif': 'image/gif',
  'pdf': 'application/pdf', 'mp3': 'audio/mpeg', 'ogg': 'audio/ogg', 'webm': 'audio/webm', 'm4a': 'audio/mp4',
  'aac': 'audio/mp4', 'mp4': 'video/mp4', 'txt': 'text/plain', 'doc': 'application/msword',
  'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'xls': 'application/vnd.ms-excel', 'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  'pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
};

String? mimeFor(String name) {
  final i = name.lastIndexOf('.');
  return i < 0 ? null : _mimes[name.substring(i + 1).toLowerCase()];
}

const allowedExtensions = ['jpg', 'jpeg', 'png', 'webp', 'gif', 'pdf', 'mp3', 'ogg', 'm4a', 'mp4', 'txt', 'doc', 'docx', 'xls', 'xlsx', 'pptx'];

/// Photo from the camera or the gallery, re-encoded as JPEG by the picker.
Future<Picked?> pickPhoto({bool camera = false}) async {
  final x = await ImagePicker().pickImage(
      source: camera ? ImageSource.camera : ImageSource.gallery, imageQuality: 85, maxWidth: 2200, maxHeight: 2200);
  if (x == null) return null;
  final bytes = await x.readAsBytes();
  var name = x.name.isEmpty ? 'photo.jpg' : x.name;
  var mime = x.mimeType ?? mimeFor(name) ?? 'image/jpeg';
  if (!mime.startsWith('image/') || mimeFor(name) == null) {
    name = '${name.split('.').first}.jpg';
    mime = 'image/jpeg';
  }
  return Picked(bytes, name, mime, kind: 'image');
}

/// Any document the server accepts.
Future<Picked?> pickDocument() async {
  final r = await FilePicker.pickFiles(type: FileType.custom, allowedExtensions: allowedExtensions);
  if (r.isEmpty) return null;
  final f = r.first;
  final bytes = await f.readAsBytes();
  final mime = mimeFor(f.name) ?? 'application/octet-stream';
  return Picked(bytes, f.name, mime, kind: mime.startsWith('image/') ? 'image' : 'file');
}

/// Voice notes: AAC in .m4a (uploaded as audio/mp4) on phones; Opus/WebM in browsers that can't record AAC.
class VoiceRecorder {
  final _rec = AudioRecorder();
  DateTime? _startedAt;
  bool _webm = false;

  Future<bool> start() async {
    if (!await _rec.hasPermission()) return false;
    _webm = kIsWeb && !await _rec.isEncoderSupported(AudioEncoder.aacLc);
    final path = kIsWeb ? '' : '${(await getTemporaryDirectory()).path}/voice_${DateTime.now().millisecondsSinceEpoch}.m4a';
    await _rec.start(
      RecordConfig(encoder: _webm ? AudioEncoder.opus : AudioEncoder.aacLc, bitRate: 64000, sampleRate: 44100, numChannels: 1),
      path: path,
    );
    _startedAt = DateTime.now();
    return true;
  }

  Duration get elapsed => _startedAt == null ? Duration.zero : DateTime.now().difference(_startedAt!);

  Future<Picked?> stop() async {
    final path = await _rec.stop();
    _startedAt = null;
    if (path == null) return null;
    final bytes = await XFile(path).readAsBytes();
    if (bytes.isEmpty) return null;
    final stamp = DateTime.now().millisecondsSinceEpoch;
    return _webm
        ? Picked(bytes, 'voice_$stamp.webm', 'audio/webm', kind: 'voice')
        : Picked(bytes, 'voice_$stamp.m4a', 'audio/mp4', kind: 'voice');
  }

  Future<void> cancel() async {
    _startedAt = null;
    await _rec.cancel();
  }

  Future<void> dispose() => _rec.dispose();
}
