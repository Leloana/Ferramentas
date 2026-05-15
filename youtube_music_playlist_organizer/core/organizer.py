class Organizer:
    def group_by_genre(self, tracks):
        grouped = {}
        for track in tracks:
            genre = track['genre']
            if genre not in grouped:
                grouped[genre] = []
            grouped[genre].append(track)
        return grouped
