"""Helper CLI to generate and exchange a Dribbble OAuth Access Token."""

import sys
import httpx


def exchange_dribbble_token():
    print("=" * 60)
    print("Dribbble OAuth 2.0 Access Token Generator")
    print("=" * 60)

    client_id = input("Enter your Dribbble Client ID: ").strip()
    if not client_id:
        print("Client ID is required.")
        return

    client_secret = input("Enter your Dribbble Client Secret: ").strip()
    if not client_secret:
        print("Client Secret is required.")
        return

    redirect_uri = input("Enter your Redirect URI (as entered in Dribbble app, e.g. http://localhost:1923): ").strip()
    if not redirect_uri:
        redirect_uri = "http://localhost:1923"

    auth_url = (
        f"https://dribbble.com/oauth/authorize?"
        f"client_id={client_id}&redirect_uri={redirect_uri}&scope=public"
    )

    print("\nStep 1: Open this authorization URL in your browser:\n")
    print(auth_url)
    print("\nClick 'Authorize'. Dribbble will redirect you to your redirect URL.")
    print("Look at the browser address bar after redirection.")
    print("Example: http://localhost:1923/?code=4f8b9e...\n")

    code = input("Paste the 'code' parameter from the address bar: ").strip()
    if not code:
        print("Authorization code is required.")
        return

    print("\nStep 2: Exchanging code for Access Token...")
    try:
        res = httpx.post(
            "https://dribbble.com/oauth/token",
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
            },
            timeout=15.0,
        )
        if res.status_code == 200:
            data = res.json()
            token = data.get("access_token")
            print("\n" + "=" * 60)
            print("SUCCESS! Your Dribbble Access Token is:")
            print("=" * 60)
            print(f"\nDRIBBBLE_ACCESS_TOKEN={token}\n")
            print("Copy and paste this into your .env file!")
            print("=" * 60)
        else:
            print(f"\nError from Dribbble (HTTP {res.status_code}):")
            print(res.text)
    except Exception as err:
        print(f"Failed to connect to Dribbble: {err}")


if __name__ == "__main__":
    exchange_dribbble_token()
