function copyPassword() {
    const passField = document.getElementById("password");
    navigator.clipboard.writeText(passField.value).then(() => {
      alert("Password copied to clipboard!");
    }).catch(err => {
      console.error("Failed to copy: ", err);
    });
  }