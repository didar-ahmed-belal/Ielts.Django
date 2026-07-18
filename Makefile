.PHONY: up down restart logs bash superuser collectstatic start GIT


down:
	docker compose down

restart:
	docker compose down
	docker compose build
	docker compose up -d
	docker compose logs -f

logs:
	docker compose logs -f


GIT:
	@# Run the whole flow in a single bash shell so `read` and the variable live in the same shell
	@bash -lc 'if [ -z "$$ (git status --porcelain)" ]; then echo "No changes to commit."; exit 0; fi; read -p "Enter commit message: " msg; git add .; git commit -m "$$msg"; git push origin main'