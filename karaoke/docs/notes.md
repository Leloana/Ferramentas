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

2. Problemas com a musica Holiday
 - [01:48.03]On holiday
    [01:49.23]
    [02:57.90](Hey!)
    [02:59.48](The representative from California has the floor)

    Em 02:27 o audio vocal.mp3 claramente fala (The representative from California has the floor), mesmo assim ele nao identifica o tempo correto

3. Checar se a funcao de baixar a musica esta limpa e esta seguindo a melhor ordem de execucao, por exemplo o que eh melhor?
Fazer o vocal e o backing primeiro? como seguir?

4. Questao do VAD, ele é melhor mesmo? estou tendo alguns problemas de compactação de tempo 
[01:46.79]On holiday
[01:46.91]Hear the drum pounding out of time
[01:47.03]Another protester has crossed the line (hey!)
[01:47.15]To find the money's on the other side
[01:47.27]Can I get another amen? (Amen!)
[01:47.39]There's a flag wrapped around a score of men (hey!)
[01:47.51]A gag, a plastic bag on a monument
[01:47.63]I beg to dream and differ from the hollow lies
[01:47.75]This is the dawning of the rest of our lives
[01:47.87]On holiday

Claramente um erro

5. Tem diferenca no fluxo de baixar a musica a primeira vez e reinstalar? Por que parece que baixar a primeira vez tem um resultado melhor

6. Pelo que eu percebi do audio vocal isolado é bem possível que o algoritmo que gera o .lrc fique melhor, o vocal.mp3 está com uma qualidade bem alta


