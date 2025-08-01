# 標準ライブラリ
import json  # JSON形式データのエンコード/デコード
import logging  # ロギング機能
import os  # OSレベルの機能を扱う
import time  # 時間に関する機能
import requests
from collections import defaultdict  # デフォルト値を持つ辞書


# Flask関連ライブラリ
from flask import Flask  # Flask本体
from flask import jsonify  # JSONレスポンス生成
from flask import render_template  # HTMLテンプレートレンダリング
from flask import request  # HTTPリクエストオブジェクト
from flask import send_from_directory  # ファイル送信
from flask import url_for  # URL生成

# Spotify APIクライアント
from spotipy.oauth2 import SpotifyClientCredentials  # Spotify OAuth2認証
from spotipy import Spotify  # Spotify API本体

from threading import Lock
from functools import lru_cache


# 環境変数を一度だけ読み取る。これらの変数はAPI認証に使用される。
# 存在しない場合はNoneを設定。
SPOTIFY_CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID", None)  # Spotify API
SPOTIFY_CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET", None)


app = Flask(__name__)


# カスタムフィルターを追加
@app.template_filter("number_format")
def number_format(value):
    return "{:,}".format(value)


# グローバル変数とロックを初期化
spotify_client = None
client_lock = Lock()

# playlists変数の初期化
playlists = None
playlists_grouped = defaultdict(
    list
)  # カテゴリごとにプレイリストを整理する辞書の初期化

# default_playlist_id変数の初期化
default_playlist_id = None


# JSONファイルを読み込む
try:
    with open("config/playlists.json", "r", encoding="utf-8") as f:
        # JSON全体をロード
        playlists_data = json.load(f)

    # カテゴリごとにプレイリストを整理
    playlists_grouped = {
        category: [(id, name) for id, name in playlists.items()]
        for category, playlists in playlists_data.items()
    }

    # 最初のカテゴリの最初のプレイリストIDをデフォルトに設定
    first_category = next(iter(playlists_grouped.keys()))
    default_playlist_id = playlists_grouped[first_category][0][0]

except FileNotFoundError:
    print("playlists.jsonが見つかりません。")
except json.JSONDecodeError:
    print("playlists.jsonの形式が不正です。")


# APIキーをチェック
def check_api_keys():
    if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
        raise ValueError(
            "Spotifyの認証情報が設定されていません。環境変数で設定してください。"
        )


# Spotify API Clientを生成して返す。言語設定はしない。
def get_spotify_client():
    global spotify_client
    with client_lock:
        if not spotify_client:
            spotify_client = Spotify(
                client_credentials_manager=SpotifyClientCredentials(
                    client_id=SPOTIFY_CLIENT_ID, client_secret=SPOTIFY_CLIENT_SECRET
                ), language = "ja",
            )
        return spotify_client


# トラックのIDリストからオーディオ特性をバッチで取得する関数
# 引数: track_ids (Spotify APIから取得したトラックIDのリスト)
# 戻り値: トラックIDをキーとし、各トラックのオーディオ特性データを含む辞書
def get_tracks_audio_features(track_ids):
    sp = get_spotify_client()  # Spotifyクライアントを取得
    features_dict = {}

    # トラックIDのリストを50曲ずつのバッチに分割し、各バッチごとにオーディオ特性を取得
    for i in range(0, len(track_ids), 50):
        batch = track_ids[i:i + 50]
        features_list = sp.audio_features(batch)  # オーディオ特性を取得
        for feature in features_list:
            if feature:
                features_dict[feature["id"]] = feature  # 特性を辞書に追加
    return features_dict


# トラック情報を取得する関数
# 引数: track (Spotify APIから取得したトラックの辞書)
# 戻り値: トラック情報を含む辞書
# キャメロットキーに対応する色のマッピング
camelot_colors = {
    "1A": "#70ECD4",  # 明るいターコイズブルー
    "1B": "#00EDC9",  # 鮮やかなシアン
    "2A": "#92F0A4",  # 淡いライムグリーン
    "2B": "#27EC82",  # 鮮烈な蛍光グリーン
    "3A": "#B1EE86",  # 柔らかい黄緑色
    "3B": "#85ED4E",  # 明るい草色
    "4A": "#E6E0A2",  # 薄いサンドカラー
    "4B": "#E0C86E",  # ゴールデンイエロー
    "5A": "#FEC8AC",  # サーモンピンク
    "5B": "#FFA279",  # 明るいコーラルレッド
    "6A": "#FFB3BF",  # 柔らかいピンク
    "6B": "#FF8C93",  # 明るいピンクレッド
    "7A": "#FFB4D2",  # ペールピンク
    "7B": "#FF85B4",  # フューシャピンク
    "8A": "#EBB7F9",  # 淡いラベンダー
    "8B": "#F087D9",  # 明るいマゼンタ
    "9A": "#E7B6F8",  # 淡いパープル
    "9B": "#CE93FF",  # 明るいライラック
    "10A": "#C0CEFB",  # 柔らかいスカイブルー
    "10B": "#A1B9FF",  # 明るいサファイアブルー
    "11A": "#94E5F8",  # 明るいシアンブルー
    "11B": "#3ED2F8",  # 鮮やかなアクアマリン
    "12A": "#50EBF0",  # 水色
    "12B": "#01EDED",  # トルコ石色
}


def camelot_key(key, mode):
    # キャメロット・ホイールに基づくキーの変換テーブル
    camelot_map = {
        # Major keys
        (0, 1): "8B",
        (1, 1): "3B",
        (2, 1): "10B",
        (3, 1): "5B",
        (4, 1): "12B",
        (5, 1): "7B",
        (6, 1): "2B",
        (7, 1): "9B",
        (8, 1): "4B",
        (9, 1): "11B",
        (10, 1): "6B",
        (11, 1): "1B",
        # Minor keys
        (0, 0): "5A",
        (1, 0): "12A",
        (2, 0): "7A",
        (3, 0): "2A",
        (4, 0): "9A",
        (5, 0): "4A",
        (6, 0): "11A",
        (7, 0): "6A",
        (8, 0): "1A",
        (9, 0): "8A",
        (10, 0): "3A",
        (11, 0): "10A",
    }

    # キーと調を数値で取得し、対応するキャメロット・キーを返す
    return camelot_map.get((key, mode), "N/A")


def get_track_info(track, audio_features):
    try:
        image_url = (
            track["album"]["images"][0]["url"]
            if track["album"]["images"]
            else url_for("static", filename="tunenest.jpg", _external=True)
        )

        spotify_link = track["external_urls"]["spotify"]
        artist_name = track["artists"][0]["name"]
        artist_id = track["artists"][0]["id"]  # アーティストIDを取得
        tempo = audio_features["tempo"] if audio_features else "不明"

        # キーと調を解析
        key_map = [
            "C",
            "C#/Db",
            "D",
            "D#/Eb",
            "E",
            "F",
            "F#/Gb",
            "G",
            "G#/Ab",
            "A",
            "A#/Bb",
            "B",
        ]
        key = (
            key_map[audio_features["key"]]
            if audio_features and "key" in audio_features
            else "N/A"
        )
        mode = "Maj" if audio_features and audio_features.get("mode") == 1 else "min"

        # キーと調を組み合わせて文字列を作成
        key_signature = f"{key} {mode}"

        # キャメロットキーの追加
        camelot_key_signature = camelot_key(
            audio_features["key"], audio_features["mode"]
        )
        camelot_color = camelot_colors.get(camelot_key_signature, "#FFFFFF")

        # トラック情報を辞書でまとめる
        track_info = {
            "id": track["id"],
            "url": track["preview_url"],
            "name": track["name"],
            "artist": artist_name,
            "artist_id": artist_id,  # アーティストIDを追加
            "image_url": image_url,
            "spotify_link": spotify_link,
            "tempo": tempo,
            "key_signature": key_signature,  # 追加されたキー情報
            "camelot_key_signature": camelot_key_signature,  # キャメロットキー
            "camelot_color": camelot_color,  # キャメロットのカラーコード
        }
        return track_info
    except KeyError as e:
        logging.warning(f"不良データを検出: {e}")
        return None  # 不良データを無視


# robots.txtファイルを返すルート。
# Flaskのstaticフォルダからファイルを送信します。
@app.route("/robots.txt")
def static_from_root():
    return send_from_directory(app.static_folder, "robots.txt")


def camelot_to_sort_key(camelot_key):
    # Camelot Keyを数値に変換する
    if camelot_key == "N/A":
        return float("inf")  # N/Aを最後に配置
    key_number, scale = int(camelot_key[:-1]), camelot_key[-1]
    # Aは偶数、Bは奇数として処理
    scale_number = 0 if scale == "A" else 1
    # 10A なら 10 * 2 = 20, 10B なら 10 * 2 + 1 = 21
    return key_number * 2 + scale_number


def format_tempo(tempo):
    return round(float(tempo), 0)


# インデックスページのルーティング処理
@app.route("/")
def index():
    try:
        # Spotifyクライアントを取得
        sp = get_spotify_client()

        keyword = request.args.get("keyword")  # クエリからキーワードを受け取る
        search_type = request.args.get(
            "search_type", "track"
        )  # クエリから検索タイプを受け取る

        # デフォルトIDかクエリパラメータIDを設定
        playlist_id = request.args.get("playlist_id", default_playlist_id)

        if keyword:
            if search_type == "album":
                # アルバム検索処理
                results = sp.search(q=keyword, type="album", limit=1, market="JP")
                if not results["albums"]["items"]:
                    return render_template("index.html", error="検索結果がありません。")

                album = results["albums"]["items"][0]
                album_id = album["id"]

                # アルバムの楽曲を取得
                album_tracks = sp.album_tracks(album_id, market="JP")
                all_tracks = album_tracks["items"]

                # アルバムのアートワークを各楽曲のアートワークとして設定
                for track in all_tracks:
                    track["album"] = album  # アルバム情報を各トラックに追加

                total_results = album_tracks["total"]

                # 検索結果が50件を超える場合、次の50件を追加で取得
                while len(all_tracks) < total_results:
                    additional_results = sp.album_tracks(
                        album_id, offset=len(all_tracks), market="JP"
                    )
                    all_tracks.extend(additional_results["items"])

                track_ids = [track["id"] for track in all_tracks]

                # 検索結果の説明メッセージを設定
                if total_results == 0:
                    playlist_description = "検索結果がありません。"
                elif total_results > 100:
                    playlist_description = f"収録曲数は{total_results}曲ありますが、最初の100曲のみ表示しています。"
                else:
                    playlist_description = f"収録曲数は{total_results}曲です。"

                playlist_name = album["name"]
                collage_filename = (
                    album["images"][0]["url"]
                    if album["images"]
                    else url_for("static", filename="tunenest.jpg", _external=True)
                )
                playlist_url = album["external_urls"]["spotify"]
                exceeds_max_tracks = False
                playlist_followers = None

            else:
                # キーワードに基づいて楽曲を検索し、まず最初の50件を取得
                results = sp.search(q=keyword, type="track", limit=50, market="JP")
                track_ids = [track["id"] for track in results["tracks"]["items"]]
                total_results = results["tracks"]["total"]  # 検索結果の総件数

                # 最初の50件を結果リストに格納
                all_tracks = results["tracks"]["items"]

                # 検索結果が50件を超える場合、次の50件を追加で取得
                if total_results > 50:
                    additional_results = sp.search(
                        q=keyword, type="track", limit=50, offset=50, market="JP"
                    )
                    all_tracks.extend(additional_results["tracks"]["items"])
                    track_ids.extend(
                        [track["id"] for track in additional_results["tracks"]["items"]]
                    )

                # 検索結果の説明メッセージを設定
                if total_results == 0:
                    playlist_description = "検索結果がありません。"
                elif total_results > 100:
                    playlist_description = f"検索結果は{total_results}曲ありますが、最初の100曲のみ表示しています。"
                else:
                    playlist_description = f"検索結果は{total_results}曲です。"

                # キーワード検索の結果を all_tracks として扱う
                all_tracks = [{"track": track} for track in results["tracks"]["items"]]
                playlist_name = keyword
                collage_filename = url_for(
                    "static", filename="tunenest.jpg", _external=True
                )
                playlist_url = ""
                exceeds_max_tracks = False
                playlist_followers = None
        else:
            # プレイリストの詳細情報を取得
            playlist_details = sp.playlist(playlist_id, market="JP")

            # プレイリストのフォロワー数を取得
            playlist_followers = playlist_details["followers"]["total"]

            # クエリパラメータからプレイリスト説明を取得
            custom_description = request.args.get("description")
            if custom_description:
                playlist_description = custom_description
            else:
                # プレイリストのdescriptionを取得
                playlist_description = playlist_details.get(
                    "description", "No description"
                )

            # プレイリストのURLを取得
            playlist_url = playlist_details.get("external_urls", {}).get("spotify", "#")

            # 現実のプレイリスト名を取得
            actual_playlist_name = playlist_details.get("name", "No playlist name")

            # クエリパラメータか現実のプレイリスト名を取得
            # ドロップリストではプレイリスト名を渡していないので
            # 通常クエリパラメータを与えられることはありません
            playlist_name = request.args.get("playlist_name", actual_playlist_name)

            # クエリパラメータからカバー画像のURLを取得
            custom_artwork_img = request.args.get("artwork_img")

            # プレイリストのカバー画像URLを安全に取得
            collage_filename = url_for(
                "static", filename="tunenest.jpg", _external=True
            )  # デフォルト値
            if custom_artwork_img:
                collage_filename = url_for(
                    "static", filename=custom_artwork_img, _external=True
                )
            elif playlist_details.get("images") and playlist_details["images"]:
                # プレイリストのimagesが存在し、空のリストでないことを確認
                collage_filename = playlist_details["images"][0].get(
                    "url", collage_filename
                )

            # プレイリストのトラックを取得
            MAX_TRACKS = 500  # 最大取得曲数を定義

            offset = 0
            limit = 100  # 1回のAPI呼び出しで取得できる最大トラック数
            all_tracks = []  # 全トラックを格納するリスト

            exceeds_max_tracks = False  # 500曲以上かどうかのフラグ

            while True:
                results = sp.playlist_tracks(
                    playlist_id, offset=offset, limit=limit, market="JP"
                )
                if results is None or results["items"] is None:
                    raise ValueError("Spotify APIが正常な値を返しませんでした。")

                all_tracks.extend(results["items"])

                # 上限に達した場合、ループを抜ける
                if len(all_tracks) > MAX_TRACKS:
                    exceeds_max_tracks = True
                    all_tracks = all_tracks[:MAX_TRACKS]
                    break

                # 全てのトラックを取得した場合、ループを抜ける
                if len(results["items"]) < limit:
                    break

                offset += limit

            # トラックIDのリストを作成し、オーディオ特性を取得
            track_ids = [
                item["track"]["id"]
                for item in all_tracks
                if item.get("track") and item["track"].get("id")
            ]

        # オーディオ特性を取得
        audio_features_dict = get_tracks_audio_features(track_ids)

        # トラック情報を整形（抜け番対応とNoneチェック）
        all_tracks_info = []
        tracks_needing_retry = []

        for item in all_tracks:
            track = item.get("track", item)  # トラック検索とアルバム検索の両方に対応
            if track and track["id"] in audio_features_dict:
                # 対応するオーディオ特性を取得
                track_features = audio_features_dict[track["id"]]
                # トラックのpopularityスコアを取得
                popularity = track.get("popularity", 0)  # 万が一popularityがない場合0を
                if popularity == 0:
                    tracks_needing_retry.append(track["id"])

                # オーディオ特性とpopularityを引数として渡す
                track_info = get_track_info(track, track_features)
                track_info["popularity"] = (
                    popularity  # popularity情報をtrack_infoに追加
                )
                if track_info is not None:  # track_infoがNoneでないことを確認
                    all_tracks_info.append(track_info)

        # バッチでトラック詳細情報を取得
        if tracks_needing_retry:
            batch_size = 50
            for i in range(0, len(tracks_needing_retry), batch_size):
                batch_ids = tracks_needing_retry[i:i + batch_size]
                try:
                    detailed_tracks = sp.tracks(batch_ids)["tracks"]
                    for detailed_track in detailed_tracks:
                        for track_info in all_tracks_info:
                            if track_info["id"] == detailed_track["id"]:
                                track_info["popularity"] = detailed_track["popularity"]
                except Exception as retry_error:
                    logging.error(
                        f"Failed to update popularity for batch: {retry_error}"
                    )

        # 有効なトラック情報のみをフィルタリング
        valid_tracks_info = [track for track in all_tracks_info if track]

        sort_order = request.args.get("order", "asc")  # デフォルトは昇順
        reverse_sort = True if sort_order == "desc" else False

        # トラックソートの処理
        # クエリパラメータから 'sort' の値を取得、デフォルトは None または ''
        sort_by = request.args.get("sort", default=None)
        if sort_by == "bpm":
            # ソート基準を BMP と Camelot Key で行う
            valid_tracks_info.sort(
                key=lambda x: (
                    format_tempo(x["tempo"]),
                    camelot_to_sort_key(x["camelot_key_signature"]),
                ),
                reverse=reverse_sort,
            )
        elif sort_by == "camelot":
            # ソート基準を Camelot Key と BPM で行う
            valid_tracks_info.sort(
                key=lambda x: (
                    camelot_to_sort_key(x["camelot_key_signature"]),
                    format_tempo(x["tempo"]),
                ),
                reverse=reverse_sort,
            )
        elif sort_by == "popularity":
            valid_tracks_info.sort(key=lambda x: x["popularity"], reverse=reverse_sort)

        # HTMLテンプレートをレンダリング
        return render_template(
            "index.html",
            playlist_name=playlist_name,
            playlists_grouped=playlists_grouped,  # 追加
            tracks=valid_tracks_info,
            collage_filename=collage_filename,
            playlist_description=playlist_description,
            playlist_url=playlist_url,
            exceeds_max_tracks=exceeds_max_tracks,
            default_playlist_id=default_playlist_id,
            playlist_followers=playlist_followers,
        )
    except Exception as e:
        # エラーページを表示
        error_str = str(e)
        if "Unsupported URL / URI" in error_str:
            user_message = (
                "Invalid or private playlist ID."
                "Please confirm your playlist ID or make it public."
            )
        else:
            user_message = (
                "An unknown error occurred.<br>" "Please go back and try again."
            )
        return render_template("error.html", error=user_message)


# アーティストの詳細情報とトップ曲、最新のアルバムを取得
# 引数: artist_id (SpotifyのアーティストID)
# 戻り値: アーティストの詳細、トップ曲のリスト、最新のアルバムの詳細を含む辞書
# キャッシュを適用
@lru_cache(maxsize=128)  # キャッシュのサイズを適宜設定
def get_cached_artist_details(artist_id, sp):
    # 既に取得したSpotifyクライアントを使用する
    artist = sp.artist(artist_id)
    return {
        "id": artist["id"],
        "name": artist["name"],
        "image_url": artist["images"][0]["url"] if artist["images"] else None,
        "popularity": artist["popularity"],
        "genres": artist["genres"],
        "followers": artist["followers"]["total"],
        "external_urls": artist["external_urls"],
    }


def get_artist_details(artist_id):
    # Spotifyクライアントを取得
    sp = get_spotify_client()

    # キャッシュされたアーティストの基本情報を取得
    artist_details = get_cached_artist_details(artist_id, sp)

    # アーティストのトップ曲を取得
    # === Spotipy版（現在は非使用、将来バージョンアップ時に再検討） ===
    # 理由：spotipy.artist_albums()がmarket未対応、日本語表記が取得できない
    # top_tracks = sp.artist_top_tracks(artist_id, country="JP")["tracks"]

    # === 現在使用しているrequests版 ===
    access_token = sp.auth_manager.get_access_token(as_dict=False)
    headers = {
        "Authorization": f"Bearer {access_token}"
    }
    params = {
        "market": "JP"  # ← countryではなくmarket！
    }
    url = f"https://api.spotify.com/v1/artists/{artist_id}/top-tracks"
    response = requests.get(url, headers=headers, params=params)
    top_tracks = response.json()["tracks"]
    # === 現在使用しているrequests版 ===

    top_tracks_details = [
        {"name": track["name"], "id": track["id"]} for track in top_tracks
    ]

    # アーティストのアルバムを取得し、最新のアルバムを特定
    # === Spotipy版（現在は非使用、将来バージョンアップ時に再検討） ===
    # 理由：spotipy.artist_albums()がmarket未対応、日本語表記が取得できない
    # albums = sp.artist_albums(artist_id, include_groups="album")["items"]

    # === 現在使用しているrequests版 ===
    access_token = sp.auth_manager.get_access_token(as_dict=False)
    headers = {
        "Authorization": f"Bearer {access_token}"  # spotipyから取り出せる
    }
    params = {
        "include_groups": "album",
        "market": "JP",
        "limit": 20
    }
    url = f"https://api.spotify.com/v1/artists/{artist_id}/albums"
    response = requests.get(url, headers=headers, params=params)
    albums = response.json()["items"]
    # === 現在使用しているrequests版 ===

    latest_album = albums[0] if albums else None
    latest_album_details = (
        {"name": latest_album["name"], "id": latest_album["id"], "artist_id": artist_id}
        if latest_album
        else None
    )

    # アーティストのSpotifyページへのリンクを追加
    spotify_url = artist_details.get("external_urls", {}).get("spotify")

    # 関連アーティストを取得
    related_artists = sp.artist_related_artists(artist_id)["artists"]
    related_artists_details = [
        {"name": artist["name"], "id": artist["id"]} for artist in related_artists
    ]

    return (
        artist_details,
        top_tracks_details,
        latest_album_details,
        related_artists_details,
        spotify_url,
    )


# アルバムIDを使用してアルバムの詳細情報を取得
# 引数: album_id (SpotifyのアルバムID)
# 戻り値: アルバムの詳細情報を含む辞書
def get_album_details(album_id):
    # Spotifyクライアントの取得
    sp = get_spotify_client()

    # アルバムIDを使用してアルバム情報を取得
    album = sp.album(album_id, market="JP")

    # 収録曲リストを作成
    tracks = [
        {"name": track["name"], "length": track["duration_ms"], "id": track["id"]}
        for track in album["tracks"]["items"]
    ]

    # アルバムの詳細情報を辞書で整理
    details = {
        "name": album["name"],  # アルバム名
        "release_date": album["release_date"],  # リリース日
        "image": album["images"][0]["url"],  # ジャケット画像のURL
        "artists": [
            {"name": artist["name"], "id": artist["id"]} for artist in album["artists"]
        ],  # 参加アーティスト
        "tracks": tracks,  # 収録曲リスト
        "popularity": album["popularity"],  # 人気度
    }

    # 詳細情報を整理して返却
    return details


# 曲のIDを受け取り、その曲の詳細情報とオーディオ特性を返す
# (タイムアウト対応版)
# 引数: song_id (Spotifyの曲ID)
# 戻り値: 曲の詳細情報とオーディオ特性を含む辞書。
# 最大リトライ回数を超えた場合はエラーをスローする。
@lru_cache(maxsize=128)
def get_cached_track(song_id, sp):
    return sp.track(song_id)


@lru_cache(maxsize=128)
def get_cached_audio_features(song_id, sp):
    return sp.audio_features([song_id])[0]


def normalize_loudness(loudness):
    """Normalize the loudness level from a dB scale of -60 to 0 to a scale of 0 to 100."""
    if loudness < -60:
        loudness = -60  # Ensure the loudness does not go below -60 dB
    elif loudness > 0:
        loudness = 0  # Ensure the loudness does not go above 0 dB
    return (loudness + 60) / 0.6  # Normalize to 0-100 scale


def get_song_details_with_retry(song_id, max_retries=3, delay=5):
    retries = 0
    while retries <= max_retries:
        try:
            sp = get_spotify_client()  # Spotifyクライアントの取得
            song_details = get_cached_track(song_id, sp)  # 曲の基本情報を取得

            # 曲のオーディオ特性を取得
            audio_features = get_cached_audio_features(song_id, sp)

            # アルバムのアートワークURLを取得
            album_artwork_url = song_details["album"]["images"][0]["url"]

            # アルバム名を取得
            album_name = song_details["album"]["name"]

            # アルバムidを取得
            album_id = song_details["album"]["id"]

            # リリース日を取得
            release_date = song_details["album"]["release_date"]

            # アーティスト名を取得（複数の場合あり）
            artists = [
                {"name": artist["name"], "id": artist["id"]}
                for artist in song_details["artists"]
            ]

            # キャメロットキーを計算
            camelot_key_value = camelot_key(
                audio_features["key"], audio_features["mode"]
            )

            # ラウドネスの生の値と正規化された値を取得
            loudness_raw = audio_features["loudness"]
            loudness_normalized = normalize_loudness(loudness_raw)

            # 成功した場合、曲の詳細情報を返す
            return {
                "acousticness": audio_features["acousticness"] * 100,
                "danceability": audio_features["danceability"] * 100,
                "duration": song_details["duration_ms"] / 1000,
                "energy": audio_features["energy"] * 100,
                "instrumentalness": audio_features["instrumentalness"] * 100,
                "key": audio_features["key"],
                "mode": audio_features["mode"],
                "name": song_details["name"],
                "popularity": song_details["popularity"],
                "tempo": audio_features["tempo"],
                "time_signature": audio_features["time_signature"],
                "valence": audio_features["valence"] * 100,
                "album_artwork_url": album_artwork_url,
                "artists": artists,
                "camelot_key": camelot_key_value,  # キャメロットキー
                "album_name": album_name,  # 収録作品（アルバム名）
                "album_id": album_id,  # 収録作品id （アルバムid）
                "release_date": release_date,  # 追加されたリリース日
                "liveness": audio_features["liveness"] * 100,
                "speechiness": audio_features["speechiness"] * 100,
                "loudness_normalized": loudness_normalized,
                "loudness_raw": loudness_raw,
            }
        except Exception as e:  # タイムアウトやその他の例外をキャッチ
            logging.error(f"An error occurred: {e}. Retrying...")
            retries += 1
            time.sleep(delay)  # delay秒待ってからリトライ

    raise Exception("Max retries reached")  # 最大を超えたら例外をスロー


# 総リリース数をカウントする関数
# 引数: artist_id (SpotifyのアーティストID), release_type (リリースの種類)
# 戻り値: 総リリース数
def count_total_releases(artist_id, release_type):
    sp = get_spotify_client()

    total_releases = sp.artist_albums(artist_id, include_groups=release_type)["total"]
    return total_releases


# アーティストのアルバムとその楽曲をページ単位で取得する関数
# 引数: artist_id (SpotifyのアーティストID), page (ページ番号), per_page (1ページあたりのアルバム数)
# 戻り値: アーティストのアルバムと楽曲情報を含む辞書のリスト
def get_artist_albums_with_songs(artist_id, page, per_page=10):
    sp = get_spotify_client()
    offset = (page - 1) * per_page
    limit = per_page

    # アーティストのアルバムをページ単位で取得
    # === Spotipy版（現在は非使用、将来バージョンアップ時に再検討） ===
    # 理由：spotipy.artist_albums()がmarket未対応、日本語表記が取得できない
    #albums = sp.artist_albums(
    #    artist_id, include_groups="album", offset=offset, limit=limit
    #)["items"]

    # === 現在使用しているrequests版 ===
    access_token = sp.auth_manager.get_access_token(as_dict=False)
    headers = {
        "Authorization": f"Bearer {access_token}"
    }
    params = {
        "include_groups": "album",
        "market": "JP",
        "limit": limit,
        "offset": offset
    }
    url = f"https://api.spotify.com/v1/artists/{artist_id}/albums"
    response = requests.get(url, headers=headers, params=params)
    albums = response.json()["items"]
    # === 現在使用しているrequests版 ===

    result = []

    for album in albums:
        album_info = {
            "name": album["name"],
            "release_date": album["release_date"],
            "tracks": [],
            "album_id": album["id"],  # アルバムID
            "artist_id": artist_id,  # アーティストID
            "total_tracks": album["total_tracks"],  # アルバムの総楽曲数
            "images": (
                album["images"] if "images" in album and album["images"] else None
            ),  # カバー画像情報
        }

        # 各アルバムに含まれる楽曲を取得
        album_tracks = sp.album_tracks(album["id"], market="JP")["items"]
        for track in album_tracks:
            track_name = track["name"]
            track_id = track["id"]
            album_info["tracks"].append({"name": track_name, "track_id": track_id})

        result.append(album_info)

    return result


# アーティストのシングルとその楽曲情報を取得
# 引数: artist_id (SpotifyのアーティストID), page (ページ番号), per_page (1ページあたりのアイテム数)
# 戻り値: シングル情報とその楽曲を含むリスト
def get_artist_singles_with_songs(artist_id, page, per_page=10):
    # Spotifyクライアントの取得
    sp = get_spotify_client()
    offset = (page - 1) * per_page
    limit = per_page

    # アーティストのシングルをページ単位で取得
    # === Spotipy版（現在は非使用、将来バージョンアップ時に再検討） ===
    # 理由：spotipy.artist_albums()がmarket未対応、日本語表記が取得できない
    #singles = sp.artist_albums(
    #    artist_id, include_groups="single", offset=offset, limit=limit
    #)["items"]

    # === 現在使用しているrequests版 ===
    access_token = sp.auth_manager.get_access_token(as_dict=False)
    headers = {
        "Authorization": f"Bearer {access_token}"
    }
    url = f"https://api.spotify.com/v1/artists/{artist_id}/albums"
    params = {
        "include_groups": "single",
        "market": "JP",
        "limit": limit,
        "offset": offset
    }
    response = requests.get(url, headers=headers, params=params)
    singles = response.json()["items"]
    # === 現在使用しているrequests版 ===

    result = []

    # シングル情報を取得
    for single in singles:
        single_info = {
            "name": single["name"],
            "release_date": single["release_date"],
            "tracks": [],
            "single_id": single["id"],  # シングルIDの追加
            "artist_id": artist_id,  # アーティストIDの追加
            "images": (
                single["images"] if "images" in single and single["images"] else None
            ),
        }

        # シングルに含まれる楽曲を取得
        single_tracks = sp.album_tracks(single["id"], market="JP")["items"]
        for track in single_tracks:
            track_name = track["name"]
            track_id = track["id"]
            single_info["tracks"].append({"name": track_name, "track_id": track_id})

        result.append(single_info)

    return result


# get_artist_compilations_with_songs()
# アーティストのコンピレーションアルバムとその楽曲を取得
# 引数: artist_id (SpotifyのアーティストID), page (ページ番号),
# per_page (1ページ当たりのアイテム数)
# 戻り値: コンピレーションアルバムとその楽曲情報を含むリスト
def get_artist_compilations_with_songs(artist_id, page, per_page=10):
    # Spotifyクライアントを取得
    sp = get_spotify_client()

    # ページングのためのオフセットとリミットを計算
    offset = (page - 1) * per_page
    limit = per_page

    # アーティストのコンピレーションアルバムをページ単位で取得
    # === Spotipy版（現在は非使用、将来バージョンアップ時に再検討） ===
    # 理由：spotipy.artist_albums()がmarket未対応、日本語表記が取得できない
    #compilations = sp.artist_albums(
    #    artist_id, include_groups="compilation", offset=offset, limit=limit
    #)["items"]

    # === 現在使用しているrequests版 ===
    access_token = sp.auth_manager.get_access_token(as_dict=False)
    headers = {
        "Authorization": f"Bearer {access_token}"
    }
    url = f"https://api.spotify.com/v1/artists/{artist_id}/albums"
    params = {
        "include_groups": "compilation",
        "market": "JP",
        "limit": limit,
        "offset": offset
    }
    response = requests.get(url, headers=headers, params=params)
    compilations = response.json()["items"]
    # === 現在使用しているrequests版 ===

    result = []

    # 各コンピレーションアルバムの詳細情報を取得
    for compilation in compilations:
        compilation_info = {
            "name": compilation["name"],  # アルバム名
            "release_date": compilation["release_date"],  # リリース日
            "tracks": [],  # 収録曲リスト
            "compilation_id": compilation["id"],  # コンピレーションID
            "artist_id": artist_id,  # アーティストID
            "total_tracks": compilation["total_tracks"],  # 総楽曲数
            "images": (
                compilation["images"]
                if "images" in compilation and compilation["images"]
                else None
            ),
        }

        # 各コンピレーションアルバムに含まれる楽曲を取得
        compilation_tracks = sp.album_tracks(compilation["id"], market="JP")["items"]
        for track in compilation_tracks:
            track_name = track["name"]
            track_id = track["id"]
            compilation_info["tracks"].append(
                {"name": track_name, "track_id": track_id}
            )

        result.append(compilation_info)

    return result


# アーティスト詳細ページ
@app.route("/artist/<artist_id>")
def artist_details(artist_id):
    (
        artist_details,
        top_tracks_details,
        latest_album_details,
        related_artists_details,
        spotify_url,
    ) = get_artist_details(artist_id)

    # 取得した情報を使ってテンプレートをレンダリングして返す
    return render_template(
        "artist_details.html",
        artist=artist_details,
        top_tracks=top_tracks_details,
        latest_album=latest_album_details,
        related_artists=related_artists_details,
        spotify_url=spotify_url,
    )


# アルバム詳細ページ
@app.route("/artist/<artist_id>/albums/<album_id>")
def album_details(artist_id, album_id):
    try:
        album = get_album_details(album_id)  # 既存の関数でSpotifyからアルバム情報を取得

        # アーティスト名を結合してからテンプレートに渡す準備
        artist_names = ", ".join([artist["name"] for artist in album["artists"]])

        return render_template(
            "album_details.html",
            album=album,
            artist_names=artist_names,
        )

    except Exception as e:
        return render_template("error.html", error=str(e))


@lru_cache(maxsize=32)
def cached_count_total_releases(artist_id, release_type):
    return count_total_releases(artist_id, release_type)


# 全アルバム表示ページのルーティング処理
# アーティストIDとページ番号（オプション）を引数として受け取る
@lru_cache(maxsize=128)
def cached_get_artist_albums_with_songs(artist_id, page, per_page=10):
    return get_artist_albums_with_songs(artist_id, page, per_page)


@app.route("/artist/<artist_id>/all_albums_and_songs", methods=["GET"])
@app.route("/artist/<artist_id>/all_albums_and_songs/page/<int:page>", methods=["GET"])
def all_albums_and_songs_for_artist(artist_id, page=1):
    per_page = 10  # 1ページあたりのアルバム数
    albums_with_songs = cached_get_artist_albums_with_songs(artist_id, page, per_page)

    # 総アルバム数を取得して、総ページ数を計算
    total_albums = cached_count_total_releases(artist_id, "album")
    total_pages = (total_albums + per_page - 1) // per_page

    # レンダリングされたHTMLテンプレートを返す
    return render_template(
        "albums_and_tracks_list.html",
        albums_with_songs=albums_with_songs,
        artist_id=artist_id,
        page=page,
        total_pages=total_pages,
        total_albums=total_albums,
        per_page=per_page,
    )


# 全シングル表示ページのルート
# アーティストIDとページ番号（オプション）を引数として受け取る
@lru_cache(
    maxsize=32
)  # キャッシュのサイズを32に設定します。必要に応じて調整してください。
def cached_get_artist_singles_with_songs(artist_id, page, per_page):
    return get_artist_singles_with_songs(artist_id, page, per_page)


@app.route("/artist/<artist_id>/all_singles_and_songs", methods=["GET"])
@app.route("/artist/<artist_id>/all_singles_and_songs/page/<int:page>", methods=["GET"])
def all_singles_and_songs_for_artist(artist_id, page=1):
    per_page = 10  # 1ページあたりのシングル数
    singles_with_songs = cached_get_artist_singles_with_songs(artist_id, page, per_page)

    # 総シングル数を取得し、総ページ数を計算
    total_singles = cached_count_total_releases(artist_id, "single")
    total_pages = (total_singles + per_page - 1) // per_page

    # レンダリングされたHTMLテンプレートを返す
    return render_template(
        "singles_and_tracks_list.html",
        singles_with_songs=singles_with_songs,
        artist_id=artist_id,
        page=page,
        total_pages=total_pages,
        total_singles=total_singles,
        per_page=per_page,
    )


# 全コンピレーションアルバム表示ページのルーティング処理
# アーティストIDとページ番号（オプション）を引数として受け取る
@lru_cache(maxsize=32)
def cached_get_artist_compilations_with_songs(artist_id, page, per_page=10):
    return get_artist_compilations_with_songs(artist_id, page, per_page)


@app.route("/artist/<artist_id>/all_compilations_and_songs", methods=["GET"])
@app.route(
    "/artist/<artist_id>/all_compilations_and_songs/page/<int:page>", methods=["GET"]
)
def all_compilations_and_songs_for_artist(artist_id, page=1):
    per_page = 10  # 1ページあたりのコンピレーション数
    compilations_with_songs = cached_get_artist_compilations_with_songs(
        artist_id, page, per_page
    )

    # 総コンピレーション数を取得し、総ページ数を計算
    total_compilations = cached_count_total_releases(artist_id, "compilation")
    total_pages = (total_compilations + per_page - 1) // per_page

    # レンダリングされたHTMLテンプレートを返す
    return render_template(
        "compilations_and_tracks_list.html",
        compilations_with_songs=compilations_with_songs,
        artist_id=artist_id,
        page=page,
        total_pages=total_pages,
        total_compilations=total_compilations,
        per_page=per_page,
    )


# 楽曲詳細ヘルプページのルート
# help_song_details.htmlテンプレートをレンダリングして返す
@app.route("/help_song_details")
def help_song_details():
    return render_template("help_song_details.html")


# 楽曲詳細ページのルート
# 引数: song_id (Spotifyの楽曲ID)
# get_song_details関数で楽曲の詳細を取得し、
# song_details.htmlテンプレートをレンダリングして返す
@app.route("/song_details/<song_id>", methods=["GET"])
def song_details(song_id):
    try:
        song = get_song_details_with_retry(song_id)  # Spotifyから曲情報を取得

        return render_template(
            "song_details.html",
            song=song,
            song_id=song_id,
        )

    except Exception as e:
        return render_template("error.html", error=str(e))


# キーワードでプレイリストを検索する新しいルート
@app.route("/search_playlist", methods=["GET"])
def search_playlist():
    keyword = request.args.get("keyword")
    if not keyword:
        return jsonify({"error": "No keyword provided"}), 400

    sp = get_spotify_client()

    # Spotify APIでキーワードでプレイリストを検索
    results = sp.search(q=keyword, type="playlist", limit=1, market="JP")
    if (
        not results
        or not results.get("playlists")
        or not results["playlists"].get("items")
    ):
        return jsonify({"error": "No playlists found"}), 404

    playlist = results["playlists"]["items"][0]
    playlist_id = playlist["id"]

    return jsonify({"playlist_id": playlist_id})


# キーワードでアーティストを検索する新しいルート
@app.route("/search_artist", methods=["GET"])
def search_artist():
    keyword = request.args.get("keyword")
    if not keyword:
        return jsonify({"error": "No keyword provided"}), 400

    sp = get_spotify_client()

    # Spotify APIでキーワードでアーティストを検索
    results = sp.search(q=keyword, type="artist", limit=1, market="JP")
    if not results or not results.get("artists") or not results["artists"].get("items"):
        return jsonify({"error": "No artists found"}), 404

    artist = results["artists"]["items"][0]
    artist_id = artist["id"]

    # 必要に応じて他の情報も含められますが、とりあえずartist_idのみ返す
    return jsonify({"artist_id": artist_id})


# キーワードでアルバムを検索する新しいルート
@app.route("/search_album", methods=["GET"])
def search_album():
    keyword = request.args.get("keyword")
    if not keyword:
        return jsonify({"error": "No keyword provided"}), 400

    sp = get_spotify_client()

    # Spotify APIでキーワードでアルバムを検索
    results = sp.search(q=keyword, type="album", limit=1, market="JP")
    if not results or not results.get("albums") or not results["albums"].get("items"):
        return jsonify({"error": "No albums found"}), 404

    album = results["albums"]["items"][0]
    album_id = album["id"]
    artist_id = album["artists"][0]["id"]  # 最初のアーティストのIDを取得

    # 必要に応じて他の情報も含められますが、album_idとartist_idを返す
    return jsonify({"album_id": album_id, "artist_id": artist_id})


# メインのエントリーポイント
# スクリプトが直接実行された場合に以下のコードが実行される
if __name__ == "__main__":
    check_api_keys()  # APIキーの存在をチェック
    debug_mode = False  # デバッグモードの設定
    port = int(os.environ.get("PORT", 8080))  # 環境変数からポート番号取得
    logging.basicConfig(level=logging.INFO)
    app.run(host="0.0.0.0", port=port, debug=debug_mode)  # Webアプリを起動
