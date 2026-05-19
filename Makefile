# Minimal Agent Memory System — Makefile

.PHONY: init status register start end checkpoint context clean reset test test-cli test-all

init:
	cd scripts && python3 db.py init

status:
	cd scripts && python3 db.py status

register:
	cd scripts && python3 start_agent.py ops --register
	cd scripts && python3 start_agent.py coder --register
	cd scripts && python3 start_agent.py research --register

start:
	cd scripts && python3 start_agent.py $(A)

end:
	cd scripts && python3 end_session.py $(A) $(ARGS)

checkpoint:
	cd scripts && python3 save_checkpoint.py $(CMD) $(ARGS)

context:
	cd scripts && python3 load_context.py $(A)

clean:
	rm -f memory/memory.db*
	rm -f memory/sessions/*.md
	rm -f memory/notes/*.md
	rm -f memory/checkpoints/*.md
	rm -f runtime/*.md
	rm -f runtime/.active_*

reset: clean init register
	@echo "DB reset, agents re-registered"

test:
	.venv/bin/python3 scripts/test_integration.py

test-cli:
	.venv/bin/python3 tests/test_cli.py

test-all: test test-cli
	@echo "✅ All tests passed"

tree:
	@find . -not -path './.git/*' -not -path './memory/*.db*' -not -name '__pycache__' -not -path '*/__pycache__/*' | sort
