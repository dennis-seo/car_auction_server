#!/usr/bin/env python3
"""
간단한 웹 서버 - React 앱에서 CSV 파일에 접근할 수 있도록 API 제공
"""
from http.server import HTTPServer, BaseHTTPRequestHandler
import os
import json
from urllib.parse import urlparse


class CORSRequestHandler(BaseHTTPRequestHandler):
    def end_headers(self):
        # CORS 헤더 추가
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        super().end_headers()

    def do_OPTIONS(self):
        # Preflight 요청 처리
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path

        # API: 사용 가능한 날짜 목록
        if path == '/api/dates':
            self.handle_dates()
        # API: 특정 날짜의 CSV 파일
        elif path.startswith('/api/csv/'):
            date = path.split('/')[-1]
            self.handle_csv(date)
        else:
            self.send_error(404)

    def handle_dates(self):
        """사용 가능한 경매 날짜 목록 반환"""
        try:
            files = os.listdir('sources')
            dates = []
            for file in files:
                if file.startswith('auction_data_') and file.endswith('.csv'):
                    date = file.replace('auction_data_', '').replace('.csv', '')
                    if len(date) == 6 and date.isdigit():
                        dates.append(date)

            dates.sort(reverse=True)  # 최신순

            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(dates).encode())
        except Exception as e:
            print(f"Error handling dates: {e}")
            self.send_error(500)

    def handle_csv(self, date):
        """특정 날짜의 CSV 파일 반환"""
        try:
            filename = f"auction_data_{date}.csv"
            filepath = os.path.join('sources', filename)

            if not os.path.exists(filepath):
                self.send_error(404)
                return

            self.send_response(200)
            self.send_header('Content-type', 'text/csv')
            self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
            self.end_headers()

            with open(filepath, 'rb') as f:
                self.wfile.write(f.read())
        except Exception as e:
            print(f"Error handling CSV {date}: {e}")
            self.send_error(500)


def run_server(port=8000):
    server = HTTPServer(('0.0.0.0', port), CORSRequestHandler)
    print(f"서버 시작: http://0.0.0.0:{port}")
    print("사용 가능한 엔드포인트:")
    print(f"  - GET http://0.0.0.0:{port}/api/dates (날짜 목록)")
    print(f"  - GET http://0.0.0.0:{port}/api/csv/{{date}} (CSV 파일)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n서버 종료")
        server.shutdown()


if __name__ == '__main__':
    run_server()