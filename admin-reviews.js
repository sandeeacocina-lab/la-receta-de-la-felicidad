import { firebaseConfig, firebaseSdkVersion, reviewAdminEmail } from "/firebase-config.js";

const firebaseBase = `https://www.gstatic.com/firebasejs/${firebaseSdkVersion}`;
const { initializeApp } = await import(`${firebaseBase}/firebase-app.js`);
const {
  collection,
  deleteDoc,
  doc,
  getDocs,
  getFirestore,
  query,
  serverTimestamp,
  updateDoc,
  where
} = await import(`${firebaseBase}/firebase-firestore.js`);
const {
  getAuth,
  GoogleAuthProvider,
  onAuthStateChanged,
  signInWithPopup,
  signOut
} = await import(`${firebaseBase}/firebase-auth.js`);

const app = initializeApp(firebaseConfig);
const auth = getAuth(app);
const db = getFirestore(app);
const signInButton = document.querySelector("[data-admin-sign-in]");
const signOutButton = document.querySelector("[data-admin-sign-out]");
const status = document.querySelector("[data-admin-status]");
const list = document.querySelector("[data-admin-list]");
const identity = document.querySelector("[data-admin-identity]");

function setStatus(message) {
  status.textContent = message;
}

function dateText(value) {
  if (!value || typeof value.toDate !== "function") return "Fecha pendiente";
  return new Intl.DateTimeFormat("es-ES", {
    dateStyle: "long",
    timeStyle: "short"
  }).format(value.toDate());
}

function makeButton(label, className, action) {
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = label;
  if (className) button.className = className;
  button.addEventListener("click", async () => {
    button.disabled = true;
    try {
      await action();
    } catch (error) {
      console.error(error);
      setStatus("No se ha podido completar la acción. Inténtalo de nuevo.");
      button.disabled = false;
    }
  });
  return button;
}

function renderReview(reviewDoc) {
  const review = reviewDoc.data();
  const article = document.createElement("article");
  article.className = "review-admin__card";

  const title = document.createElement("h2");
  const link = document.createElement("a");
  link.href = review.recipeUrl;
  link.target = "_blank";
  link.rel = "noopener";
  link.textContent = review.recipeTitle;
  title.append(link);

  const meta = document.createElement("p");
  meta.className = "review-admin__meta";
  meta.textContent = `${review.name} · ${review.rating} de 5 estrellas · ${dateText(review.createdAt)}`;

  const comment = document.createElement("p");
  comment.textContent = review.comment;

  const actions = document.createElement("div");
  actions.className = "review-admin__actions";
  actions.append(
    makeButton("Aprobar y publicar", "", async () => {
      await updateDoc(doc(db, "reviews", reviewDoc.id), {
        status: "approved",
        approvedAt: serverTimestamp()
      });
      article.remove();
      setStatus("Reseña aprobada y publicada.");
      showEmptyIfNeeded();
    }),
    makeButton("Eliminar", "review-admin__reject", async () => {
      await deleteDoc(doc(db, "reviews", reviewDoc.id));
      article.remove();
      setStatus("Reseña eliminada.");
      showEmptyIfNeeded();
    })
  );

  article.append(title, meta, comment, actions);
  return article;
}

function showEmptyIfNeeded() {
  if (list.children.length) return;
  const empty = document.createElement("p");
  empty.dataset.adminEmpty = "";
  empty.textContent = "No hay reseñas pendientes.";
  list.append(empty);
}

async function loadPendingReviews() {
  list.replaceChildren();
  setStatus("Cargando reseñas pendientes…");
  const pendingQuery = query(
    collection(db, "reviews"),
    where("status", "==", "pending")
  );
  const snapshot = await getDocs(pendingQuery);
  const documents = snapshot.docs.slice().sort((a, b) => {
    const aTime = a.data().createdAt?.toMillis?.() || 0;
    const bTime = b.data().createdAt?.toMillis?.() || 0;
    return bTime - aTime;
  });
  documents.forEach((item) => list.append(renderReview(item)));
  setStatus(documents.length
    ? `${documents.length} reseña${documents.length === 1 ? "" : "s"} pendiente${documents.length === 1 ? "" : "s"}.`
    : "No hay reseñas pendientes.");
  showEmptyIfNeeded();
}

signInButton.addEventListener("click", async () => {
  signInButton.disabled = true;
  setStatus("Abriendo el acceso de Google…");
  try {
    await signInWithPopup(auth, new GoogleAuthProvider());
  } catch (error) {
    console.error(error);
    setStatus("No se pudo iniciar sesión con Google.");
    signInButton.disabled = false;
  }
});

signOutButton.addEventListener("click", () => signOut(auth));

onAuthStateChanged(auth, async (user) => {
  const isAdmin = Boolean(user && user.email === reviewAdminEmail && user.emailVerified);
  signInButton.hidden = Boolean(user);
  signOutButton.hidden = !isAdmin;
  identity.textContent = user?.email || "";

  if (!user) {
    signInButton.disabled = false;
    list.replaceChildren();
    setStatus("Accede con tu cuenta de Google para moderar las reseñas.");
    return;
  }

  if (!isAdmin) {
    list.replaceChildren();
    setStatus(`La cuenta ${user.email || "seleccionada"} no tiene permiso de moderación.`);
    await signOut(auth);
    return;
  }

  try {
    await loadPendingReviews();
  } catch (error) {
    console.error(error);
    setStatus("No se pudieron cargar las reseñas pendientes.");
  }
});
