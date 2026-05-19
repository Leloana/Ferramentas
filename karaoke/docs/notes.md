1. Vagalume — melhor cobertura para música brasileira, tem API gratuita com cadastro:
pythonimport requests

def fetch_vagalume(artist, title, api_key):
    url = f"https://api.vagalume.com.br/search.php"
    params = {"art": artist, "mus": title, "apikey": api_key}
    r = requests.get(url, params=params)
    data = r.json()
    if data.get("type") == "exact":
        return data["mus"][0]["text"]
    return None