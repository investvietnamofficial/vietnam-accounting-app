import 'dart:io';
import 'package:camera/camera.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:image_cropper/image_cropper.dart';
import 'package:flutter_image_compress/flutter_image_compress.dart';
import 'package:hive/hive.dart';
import 'package:uuid/uuid.dart';

import '../../core/services/api_service.dart';

/// Upload states
enum UploadStatus { idle, capturing, cropping, compressing, uploading, processing, done, error }

class ScannerState {
  final UploadStatus status;
  final String? documentId;
  final String? jobId;
  final String? errorMessage;
  final double uploadProgress;

  const ScannerState({
    this.status = UploadStatus.idle,
    this.documentId,
    this.jobId,
    this.errorMessage,
    this.uploadProgress = 0,
  });

  ScannerState copyWith({
    UploadStatus? status,
    String? documentId,
    String? jobId,
    String? errorMessage,
    double? uploadProgress,
  }) => ScannerState(
    status: status ?? this.status,
    documentId: documentId ?? this.documentId,
    jobId: jobId ?? this.jobId,
    errorMessage: errorMessage ?? this.errorMessage,
    uploadProgress: uploadProgress ?? this.uploadProgress,
  );
}

class ScannerNotifier extends StateNotifier<ScannerState> {
  final ApiService _api;
  final Box _pendingUploads;

  ScannerNotifier(this._api, this._pendingUploads) : super(const ScannerState());

  /// Full pipeline: capture → crop → compress → upload
  Future<void> captureAndUpload({
    required File imageFile,
    String docType = 'invoice_vat',
  }) async {
    try {
      // Step 1: Crop
      state = state.copyWith(status: UploadStatus.cropping);
      final cropped = await _cropImage(imageFile);
      if (cropped == null) {
        state = state.copyWith(status: UploadStatus.idle);
        return;
      }

      // Step 2: Compress
      state = state.copyWith(status: UploadStatus.compressing);
      final compressed = await _compressImage(cropped);

      // Step 3: Upload (or queue if offline)
      state = state.copyWith(status: UploadStatus.uploading, uploadProgress: 0);

      final response = await _api.uploadDocument(
        imageFile: compressed,
        docType: docType,
        onProgress: (sent, total) {
          state = state.copyWith(uploadProgress: sent / total);
        },
      );

      state = state.copyWith(
        status: UploadStatus.processing,
        documentId: response['document_id'],
        jobId: response['job_id'],
      );

    } catch (e) {
      // Queue for retry when offline
      await _queueForOfflineUpload(imageFile, docType);
      state = state.copyWith(
        status: UploadStatus.error,
        errorMessage: e.toString(),
      );
    }
  }

  Future<File?> _cropImage(File file) async {
    final cropped = await ImageCropper().cropImage(
      sourcePath: file.path,
      aspectRatioPresets: [CropAspectRatioPreset.ratio4x3],
      uiSettings: [
        AndroidUiSettings(
          toolbarTitle: 'Crop Invoice',
          toolbarColor: Colors.blue.shade800,
          toolbarWidgetColor: Colors.white,
          lockAspectRatio: false,
        ),
        IOSUiSettings(title: 'Crop Invoice'),
      ],
    );
    return cropped != null ? File(cropped.path) : null;
  }

  Future<File> _compressImage(File file) async {
    // Target: max 1200px on longest side, 85% quality → ~200-400KB
    final compressed = await FlutterImageCompress.compressAndGetFile(
      file.path,
      '${file.path}_compressed.jpg',
      quality: 85,
      minWidth: 800,
      minHeight: 600,
      format: CompressFormat.jpeg,
    );
    return compressed != null ? File(compressed.path) : file;
  }

  Future<void> _queueForOfflineUpload(File file, String docType) async {
    await _pendingUploads.put(const Uuid().v4(), {
      'file_path': file.path,
      'doc_type': docType,
      'queued_at': DateTime.now().toIso8601String(),
    });
  }

  /// Retry all pending offline uploads
  Future<void> retryPendingUploads() async {
    // TODO (Codex): Implement offline upload retry logic.
    // Iterate pendingUploads box, attempt upload, remove on success.
  }

  void reset() => state = const ScannerState();
}

final scannerProvider = StateNotifierProvider<ScannerNotifier, ScannerState>((ref) {
  final api = ref.watch(apiServiceProvider);
  final box = Hive.box('pending_uploads');
  return ScannerNotifier(api, box);
});


/// Scanner screen widget
class ScannerScreen extends ConsumerStatefulWidget {
  const ScannerScreen({super.key});

  @override
  ConsumerState<ScannerScreen> createState() => _ScannerScreenState();
}

class _ScannerScreenState extends ConsumerState<ScannerScreen> {
  CameraController? _controller;
  List<CameraDescription> _cameras = [];

  @override
  void initState() {
    super.initState();
    _initCamera();
  }

  Future<void> _initCamera() async {
    _cameras = await availableCameras();
    if (_cameras.isEmpty) return;
    _controller = CameraController(
      _cameras.first,
      ResolutionPreset.high,
      enableAudio: false,
    );
    await _controller!.initialize();
    if (mounted) setState(() {});
  }

  @override
  void dispose() {
    _controller?.dispose();
    super.dispose();
  }

  Future<void> _takePicture() async {
    if (_controller == null || !_controller!.value.isInitialized) return;
    final xFile = await _controller!.takePicture();
    await ref.read(scannerProvider.notifier).captureAndUpload(
      imageFile: File(xFile.path),
    );
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(scannerProvider);

    return Scaffold(
      backgroundColor: Colors.black,
      body: Stack(
        children: [
          // Camera preview
          if (_controller != null && _controller!.value.isInitialized)
            Positioned.fill(child: CameraPreview(_controller!))
          else
            const Center(child: CircularProgressIndicator(color: Colors.white)),

          // Invoice frame guide
          const _InvoiceFrameOverlay(),

          // Status overlay
          if (state.status != UploadStatus.idle && state.status != UploadStatus.capturing)
            _StatusOverlay(state: state),

          // Bottom controls
          Positioned(
            bottom: 40,
            left: 0,
            right: 0,
            child: _BottomControls(
              onCapture: _takePicture,
              onGallery: () {
                // TODO (Codex): Open gallery picker
              },
              isCapturing: state.status != UploadStatus.idle,
            ),
          ),
        ],
      ),
    );
  }
}

class _InvoiceFrameOverlay extends StatelessWidget {
  const _InvoiceFrameOverlay();

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Container(
        width: MediaQuery.of(context).size.width * 0.85,
        height: MediaQuery.of(context).size.width * 0.85 * 1.41, // A4 ratio
        decoration: BoxDecoration(
          border: Border.all(color: Colors.white54, width: 1.5),
          borderRadius: BorderRadius.circular(8),
        ),
        child: const Align(
          alignment: Alignment.topCenter,
          child: Padding(
            padding: EdgeInsets.only(top: 12),
            child: Text(
              'Align invoice within frame',
              style: TextStyle(color: Colors.white70, fontSize: 12),
            ),
          ),
        ),
      ),
    );
  }
}

class _StatusOverlay extends StatelessWidget {
  final ScannerState state;
  const _StatusOverlay({required this.state});

  @override
  Widget build(BuildContext context) {
    String message;
    switch (state.status) {
      case UploadStatus.cropping: message = 'Preparing crop...'; break;
      case UploadStatus.compressing: message = 'Optimising image...'; break;
      case UploadStatus.uploading:
        message = 'Uploading ${(state.uploadProgress * 100).toInt()}%';
        break;
      case UploadStatus.processing: message = 'Processing with OCR...'; break;
      case UploadStatus.done: message = 'Done!'; break;
      case UploadStatus.error: message = 'Error: ${state.errorMessage}'; break;
      default: message = '';
    }

    return Positioned.fill(
      child: Container(
        color: Colors.black54,
        child: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (state.status == UploadStatus.uploading)
                CircularProgressIndicator(value: state.uploadProgress, color: Colors.white)
              else if (state.status != UploadStatus.error && state.status != UploadStatus.done)
                const CircularProgressIndicator(color: Colors.white),
              const SizedBox(height: 16),
              Text(message, style: const TextStyle(color: Colors.white, fontSize: 16)),
            ],
          ),
        ),
      ),
    );
  }
}

class _BottomControls extends StatelessWidget {
  final VoidCallback onCapture;
  final VoidCallback onGallery;
  final bool isCapturing;

  const _BottomControls({
    required this.onCapture,
    required this.onGallery,
    required this.isCapturing,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceEvenly,
      children: [
        IconButton(
          icon: const Icon(Icons.photo_library, color: Colors.white, size: 32),
          onPressed: isCapturing ? null : onGallery,
        ),
        GestureDetector(
          onTap: isCapturing ? null : onCapture,
          child: Container(
            width: 72,
            height: 72,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              border: Border.all(color: Colors.white, width: 3),
              color: isCapturing ? Colors.grey : Colors.white24,
            ),
            child: const Icon(Icons.camera_alt, color: Colors.white, size: 36),
          ),
        ),
        const SizedBox(width: 48), // balance
      ],
    );
  }
}
