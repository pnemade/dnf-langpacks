NAME = dnf-langpacks
VERSION = $(shell python setup.py -V)

DIST = dist

SRC_FILES = LICENSE ChangeLog Makefile README.md langpacks.py setup.py dnf-langpacks.8

$(NAME)-$(VERSION).tar.gz:
	mkdir -p dist
	mkdir dist/$(NAME)-$(VERSION)
	cp -p $(SRC_FILES) dist/$(NAME)-$(VERSION)
	tar zcvf $(NAME)-$(VERSION).tar.gz -C dist $(NAME)-$(VERSION)

clean:
	rm -rf *~ dist/*
	rm -f *.gz

git-tag:
	git tag $(VERSION)

git-push:
	git push
	git push --tags

