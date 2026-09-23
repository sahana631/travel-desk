# Travel Desk

A straightforward Flask and SQLite travel desk for booking trips and organizing itinerary items.

## Run locally

```bash
python app.py
```

Then open `http://localhost:5000`.

The SQLite database is created automatically as `travel_desk.db` on first run. Set `DATABASE_PATH` to use a different database file and `SECRET_KEY` to provide a different Flask session key.

## Included

- Create an account and log in
- Book, view, edit, and delete trips
- Add flights, hotels, activities, and other itinerary items
- View itinerary items in chronological order for each trip