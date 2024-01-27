# MyAnimeList Helper
### How to run
1. Please follow step 0 [here](https://myanimelist.net/blog.php?eid=835707) to register for an MAL API key and get your **CLIENT_ID** and **CLIENT_SECRET**
2. Use the following template to create a file called `credentials.json` in the *mal_helper* folder
```
{
    "client_id": "YOUR_CLIENT_ID",
    "client_secret": "YOUR_CLIENT_SECRET"
}
```
3. Run `auth.py`. It should generate a `token.json` file in the *mal_helper* folder
4. Open `mal_helper.py` and uncomment the relevant line of code at the bottom of the script. Then run the script and follow the instructions in the console