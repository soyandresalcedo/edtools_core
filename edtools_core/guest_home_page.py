def get_website_user_home_page(user: str):
	"""Invitados en la raíz del sitio → login (evita home genérica o Web Page vacía)."""
	if user == "Guest":
		return "login"
	return None
