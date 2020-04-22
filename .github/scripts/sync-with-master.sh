#!/bin/bash -eux

#
# This variable must be passed into this script.
#
[[ -n "${BRANCH}" ]] || exit 1

#
# We need these config parameters set in order to do the git-merge.
#
git config user.name "${GITHUB_ACTOR}"
git config user.email "${GITHUB_ACTOR}@users.noreply.github.com"

#
# We need the full git repository history in order to do the git-merge.
#
git fetch --unshallow

#
# In order to open a pull request, we need to push to a remote branch.
# To avoid conflicting with existing remote branches, we use branches
# within the "sync-with-master" namespace.
#
git checkout -b "sync-with-master/${BRANCH}" "origin/${BRANCH}"
git merge -Xtheirs origin/master
git push -f origin "sync-with-master/${BRANCH}"

#
# Opening a pull request may fail if there already exists a pull request
# for the branch; e.g. if a previous pull request was previously made,
# but not yet merged by the time we run this "sync" script again. Thus,
# rather than causing the automation to report a failure in this case,
# we swallow the error and report success.
#
# Additionally, as along as the git branch was properly updated (via the
# "git push" above), the existing PR will have been updated as well, so
# the "hub" command is unnecessary (hence ignoring the error).
#
git log -1 --format=%B | hub pull-request -F - -b "${BRANCH}" || true
