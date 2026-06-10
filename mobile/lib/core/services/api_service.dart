import 'dart:io';
import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

const _storage = FlutterSecureStorage();

class ApiService {
  late final Dio _dio;

  ApiService(String baseUrl) {
    _dio = Dio(BaseOptions(baseUrl: '$baseUrl/api/v1', connectTimeout: const Duration(seconds: 15)));
    _dio.interceptors.add(InterceptorsWrapper(
      onRequest: (options, handler) async {
        final token = await _storage.read(key: 'access_token');
        if (token != null) options.headers['Authorization'] = 'Bearer $token';
        handler.next(options);
      },
    ));
  }

  Future<Map<String, dynamic>> uploadDocument({
    required File imageFile,
    String docType = 'invoice_vat',
    void Function(int, int)? onProgress,
  }) async {
    final form = FormData.fromMap({
      'file': await MultipartFile.fromFile(imageFile.path, filename: 'invoice.jpg'),
      'doc_type': docType,
    });
    final resp = await _dio.post('/documents/upload', data: form,
        onSendProgress: onProgress);
    return resp.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getDocument(String id) async {
    final resp = await _dio.get('/documents/$id');
    return resp.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> login(String email, String password) async {
    final resp = await _dio.post('/auth/token', data: {'username': email, 'password': password},
        options: Options(contentType: 'application/x-www-form-urlencoded'));
    final data = resp.data as Map<String, dynamic>;
    await _storage.write(key: 'access_token', value: data['access_token']);
    await _storage.write(key: 'refresh_token', value: data['refresh_token']);
    return data;
  }
}

final apiServiceProvider = Provider<ApiService>((ref) {
  const baseUrl = String.fromEnvironment('API_BASE_URL', defaultValue: 'http://localhost:8000');
  return ApiService(baseUrl);
});
