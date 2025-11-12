from setuptools import setup, find_packages

with open("requirements.txt") as f:
	install_requires = f.read().strip().split("\n")

setup(
	name="edtools_core",
	version="0.0.1",
	description="Custom branding and features for Edtools Educational System",
	author="Andres Salcedo",
	author_email="soyandresalcedo@gmail.com",
	packages=find_packages(),
	zip_safe=False,
	include_package_data=True,
	install_requires=install_requires
)
