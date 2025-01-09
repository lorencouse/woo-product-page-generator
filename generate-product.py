import requests
import time
import math
from woocommerce import API
from PIL import Image
import io
import base64
import json
import os
from dotenv import load_dotenv

load_dotenv()


BASE_URL = os.getenv("WOO_BASE_URL")
USERNAME = os.getenv("WOO_USERNAME")
PASSWORD = os.getenv("WOO_PASSWORD")
consumer_key = os.getenv("WOO_CONSUMER_KEY")
consumer_secret = os.getenv("WOO_CONSUMER_SECRET")
openai_token = os.getenv("OPENAI_TOKEN")
API_ENDPOINT = os.getenv("WOO_API_ENDPOINT")

data = f"{consumer_key}:{consumer_secret}"
API_KEY = base64.b64encode(data.encode()).decode()
WP_LOGIN = base64.b64encode(f"{USERNAME}:{PASSWORD}".encode()).decode()
wp_img_urls = []

# Determine the directory where the script is located
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Define the full path for the categories.json file
CATEGORY_FILE_PATH = os.path.join(SCRIPT_DIR, "categories.json")


def product_exists(sku):
    # Define your WooCommerce API endpoint and credentials
    url = "https://www.maleq.org/wp-json/wc/v3/products"
    params = {
        "sku": sku,
        "consumer_key": consumer_key,
        "consumer_secret": consumer_secret,
    }

    response = requests.get(url, params=params)
    products = response.json()

    # If the response has products, it means the SKU exists
    return len(products) > 0


# Function to get product data from the provided API
def get_product_data(sku):
    response = requests.get(
        f"http://wholesale.williams-trading.com/rest/products/{sku}?format=json"
    )
    return response.json()["product"]


def generate_description(product_name, product_description, image_urls):
    openai_url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {openai_token}",
        "Content-Type": "application/json",
    }
    data = {
        "model": "gpt-3.5-turbo",
        "messages": [
            {
                "role": "system",
                "content": f"You are a helpful assistant. Provide a detailed description for the given product. SEO optimize using {product_name} as the target keyword.",
            },
            {"role": "user", "content": f"{product_name}: {product_description}"},
        ],
    }
    response = requests.post(openai_url, headers=headers, json=data)
    response_data = response.json()

    description = ""
    if "choices" in response_data:
        description = response_data["choices"][0]["message"]["content"].strip()

    # Split description into paragraphs and filter out empty ones
    paragraphs = [para.strip() for para in description.split("\n") if para.strip()]

    # Counter for images
    image_counter = 0

    # Create a new list for the final result
    final_paragraphs = []

    # Add the first paragraph
    final_paragraphs.append(paragraphs[0] if paragraphs else "")

    # Add the <h2> tag
    final_paragraphs.append(f"<h2>{product_name}</h2>")

    # If there's an image available, insert it after the <h2> tag
    if image_counter < len(image_urls):
        final_paragraphs.append(
            f'<img src="{image_urls[image_counter]}" alt="{product_name} image {image_counter+1}"/>'
        )
        image_counter += 1

    # Append images after each subsequent paragraph
    for paragraph in paragraphs[1:]:  # Start from the second paragraph, if available
        final_paragraphs.append(paragraph)

        if image_counter < len(image_urls) and not paragraph.startswith("<img"):
            final_paragraphs.append(
                f'<img src="{image_urls[image_counter]}" alt="{product_name} image {image_counter+1}"/>'
            )
            image_counter += 1

    # If there are remaining images, append them at the end
    while image_counter < len(image_urls):
        final_paragraphs.append(
            f'<img src="{image_urls[image_counter]}" alt="{product_name} image {image_counter+1}"/>'
        )
        image_counter += 1

    # Combine paragraphs back into a single description
    modified_description = "\n\n".join(final_paragraphs)

    return modified_description


def save_categories_to_file(categories):
    with open(CATEGORY_FILE_PATH, "w") as file:
        json.dump(categories, file)


def load_categories_from_file():
    with open(CATEGORY_FILE_PATH, "r") as file:
        return json.load(file)


def fetch_all_pages(api_endpoint, headers, params):
    """Fetch all pages from an endpoint."""
    all_results = []
    page = 1

    while True:
        params["page"] = page
        response = requests.get(api_endpoint, headers=headers, params=params)

        if response.status_code != 200:
            raise Exception(
                f"Failed to fetch data from API. Status code: {response.status_code}"
            )

        data = response.json()

        if not data or page > int(response.headers.get("X-WP-TotalPages", 0)):
            break

        all_results.extend(data)
        page += 1

    return all_results


def fetch_categories():
    """Fetch categories from WooCommerce or local storage."""
    try:
        with open(CATEGORY_FILE_PATH, "r") as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        headers = {"Authorization": f"Basic {API_KEY}"}
        params = {"per_page": 100}
        categories = fetch_all_pages(
            f"{API_ENDPOINT}products/categories", headers, params
        )

        with open(CATEGORY_FILE_PATH, "w") as file:
            json.dump(categories, file)

        return categories


def get_children(categories, parent_id):
    return [cat for cat in categories if cat["parent"] == parent_id]


def select_category(categories, parent_id=0, selected_ids=[]):
    child_categories = get_children(categories, parent_id)
    if not child_categories:
        return selected_ids + [parent_id]

    for idx, category in enumerate(child_categories, 1):
        print(f"{idx}. {category['name']}")

    while True:
        choice = input(
            "Select a category, press 'r' to refetch, 'c' to confirm selection or 'x' to restart: "
        )
        if choice == "r":
            categories = fetch_categories()
            return select_category(categories, parent_id, selected_ids)
        if choice == "x":
            return select_category(categories)
        if choice == "c":
            return selected_ids + [parent_id]
        try:
            selected = child_categories[int(choice) - 1]
            return select_category(
                categories, selected["id"], selected_ids + [selected["id"]]
            )
        except (ValueError, IndexError):
            print("Invalid choice, please select a valid category.")


def main():
    while True:
        skus_input = input(
            "\nEnter product SKUs separated by space or 'exit' to stop: "
        )

        if skus_input.lower() == "exit":
            break

        skus = skus_input.split()  # Splits based on spaces by default

        categories = fetch_categories()
        selected_categories = select_category(categories)
        if selected_categories == "refetch":
            print("\nRefetching categories...")
            fetch_woocommerce_categories(refetch=True)
            selected_categories = select_category(categories)

        for sku in skus:
            product = get_product_data(sku)

            if product_exists(product["barcode"]):
                print(
                    f"A product with SKU {product['barcode']} already exists on WooCommerce. Skipping this SKU."
                )
                continue

            # Capitalize the product name
            product["name"] = product["name"].title()

            # Retrieve image URLs from product data
            image_urls = [img["image_large_url"] for img in product["images"]]

            # Modify price and sale price
            product_price = math.ceil(float(product["price"]) * 3.3 - 0.01) + 0.99
            sale_price = math.ceil(float(product["price"]) * 3 - 0.01) + 0.87

            # Extract tags from categories
            tags = [category["name"] for category in product["categories"]]

            # Output formatted data for user to check
            print(f"\nName: {product['name']}")
            print(f"SKU: {product['barcode']}")
            print(f"Description: {product['description']}")
            print(f"Price: ${product_price}")
            print(f"Sale Price: ${sale_price}")
            print(f"Manufacturer: {product['manufacturer']['name']}")
            print(f"Height: {product['height']}")
            print(f"Length: {product['length']}")
            print(f"Width: {product['width']}")
            print(f"Diameter: {product['diameter']}")
            print(f"Weight: {product['weight']}")
            print(f"Color: {product['color']}")
            print(f"Material: {product['material']}")
            print(f"Brand: {product['brand']}")
            print(f"Tags: {', '.join(tags)}")  # Printing the tags

            print("Selected Categories:", selected_categories)

            success = create_product_in_woocommerce(product, selected_categories)
            wp_img_urls.clear()


def process_and_save_image(img_url, save_name):
    response = requests.get(img_url)
    image = Image.open(io.BytesIO(response.content))

    # If the image is larger than 650x650, resize it
    if image.width > 650 or image.height > 650:
        image.thumbnail((650, 650))

    # Determine the size of the background:
    # It's either 650x650 or the maximum dimension of the image
    max_dim = max(image.width, image.height)
    background = Image.new("RGB", (max_dim, max_dim), (255, 255, 255))

    # Calculate coordinates to paste image on white background to center it
    bg_w, bg_h = background.size
    img_w, img_h = image.size
    offset = ((bg_w - img_w) // 2, (bg_h - img_h) // 2)

    background.paste(image, offset)
    background.save(save_name, "JPEG")  # Saving in JPEG format

    return save_name


def get_attributes_from_product(product):
    """Generate attributes list from a product data."""
    attributes = []

    # Check for 'manufacturer' and add if exists
    if product.get("manufacturer") and product["manufacturer"].get("name"):
        attributes.append(
            {
                "name": "Manufacturer",
                "visible": True,
                "variation": False,
                "options": [product["manufacturer"]["name"]],
            }
        )

    # Check for 'color' and add if exists
    if product.get("color"):
        attributes.append(
            {
                "name": "Color",
                "visible": True,
                "variation": False,
                "options": [product["color"]],
            }
        )

    # Check for 'material' and add if exists
    if product.get("material"):
        attributes.append(
            {
                "name": "Material",
                "visible": True,
                "variation": False,
                "options": [product["material"]],
            }
        )

    return attributes


def create_product_in_woocommerce(product, selected_categories, retries=3, delay=2):
    twofa_code = input("Enter your 2FA code: ")

    headers = {
        "Authorization": "Basic " + WP_LOGIN,
        "X-WP-2FA-Code": twofa_code,  # Add this line to include the 2FA code in the headers
    }
    attributes = get_attributes_from_product(product)
    img_ids = upload_images_to_woocommerce(product, headers)

    # Generate new description
    new_description = generate_description(
        product["name"], product["description"], wp_img_urls
    )
    product["description"] = new_description
    if float(product["price"]) <= 8:
        product["price"] = float(product["price"]) + 4
    if float(product["price"]) > 99:
        product["price"] = float(product["price"]) * 0.85

    data = {
        "name": product["name"],
        "type": "simple",
        "regular_price": str(
            math.ceil(float(product["price"]) * 3.3 - 0.01) + 0.99
        ),  # Convert float to string
        "sale_price": str(
            math.ceil(float(product["price"]) * 3 - 0.01) + 0.87
        ),  # Convert float to string
        "description": product["description"],
        "sku": product["barcode"],
        "tags": [
            {"name": tag}
            for tag in [category["name"] for category in product["categories"]]
        ],
        "categories": [{"id": cat_id} for cat_id in selected_categories],
        "attributes": attributes,
        "dimensions": {
            "height": str(product["height"]) if product.get("height") else "",
            "length": str(product["length"]) if product.get("length") else "",
            "width": str(product["width"]) if product.get("width") else "",
        },
        "weight": str(product["weight"]) if product.get("weight") else "",
        "images": [{"id": img_id} for img_id in img_ids],
    }

    for attempt in range(retries):
        try:
            response = requests.post(
                f"{BASE_URL}wc/v3/products", headers=headers, json=data
            ).json()

            if "id" in response:
                print(f"\nProduct created successfully with ID {response['id']}")
                return True  # Indicates success
            else:
                print(
                    f"\nFailed to create product. Error: {response.get('message', 'Unknown error')}"
                )
                if (
                    attempt < retries - 1
                ):  # If it's not the last attempt, sleep before the next one
                    print(f"Retrying in {delay} seconds...")
                    time.sleep(delay)
                else:
                    return False  # Indicates failure after all retries
        except requests.exceptions.RequestException as e:
            print(f"Request failed. Error: {e}")
            if attempt < retries - 1:
                print(f"Retrying in {delay} seconds...")
                time.sleep(delay)
            else:
                print("All attempts failed.")
                return False


def sanitize_filename(filename):
    invalid_chars = ["<", ">", ":", '"', "/", "\\", "|", "?", "*"]
    for char in invalid_chars:
        filename = filename.replace(char, "_")
    return filename


def upload_images_to_woocommerce(product, headers):
    session = requests.Session()
    session.headers.update(headers)

    image_urls = [img["image_large_url"] for img in product["images"]]
    print(f"Found {len(image_urls)} images for product.")

    img_ids = []

    for idx, img_url in enumerate(image_urls):
        print(f"Processing image {idx + 1}/{len(image_urls)} from URL: {img_url}")
        response = requests.get(img_url)
        if response.status_code != 200:
            print(f"Failed to download image {idx + 1} from URL: {img_url}")
            continue

        # Save the processed image
        filename = sanitize_filename(
            f"{product['name'].replace(' ', '_')}_{idx + 1}.jpg"
        )
        saved_image_path = process_and_save_image(img_url, filename)

        with open(saved_image_path, "rb") as img_file:
            img_data = {"file": (filename, img_file, "image/jpeg")}
            img_meta = {"description": filename, "alt_text": filename}

            upload_attempt = 1
            max_attempts = 3

            while upload_attempt <= max_attempts:
                try:
                    response = session.post(
                        f"{BASE_URL}wp/v2/media",
                        files=img_data,
                        data=img_meta,
                    )

                    if response.status_code == 201:
                        # Success
                        uploaded_image = response.json()
                        img_ids.append(uploaded_image["id"])
                        print(
                            f"Successfully uploaded image {idx + 1} with ID: {uploaded_image['id']}"
                        )
                        break
                    elif "wfls_twofactor_required" in response.text:
                        # Handle 2FA requirement
                        print("2FA code required.")
                        twofa_code = input("Enter your 2FA code: ")
                        session.headers.update(
                            {"X-WP-2FA-Code": twofa_code}
                        )  # Add the 2FA code to the session headers
                        continue
                    else:
                        print(
                            f"Failed to upload image {idx + 1}. Response Code: {response.status_code}. Message: {response.text}"
                        )

                except Exception as e:
                    print(
                        f"Error occurred during image upload attempt {upload_attempt}: {e}"
                    )

                upload_attempt += 1

            if upload_attempt > max_attempts:
                user_input = input("Failed to upload image. Retry? (y/n): ").lower()
                if user_input != "y":
                    break

            os.remove(saved_image_path)

    return img_ids


if __name__ == "__main__":
    main()
