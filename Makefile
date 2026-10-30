.PHONY: test test-fast
test:
	@sh scripts/test.sh

test-fast:
	@sh scripts/test.sh --fast
